import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.api import audit_log, auth, items, public, users
from app.bootstrap import ensure_admin_user
from app.config import settings
from app.database import async_session
from app.middleware.csrf import CSRFMiddleware
from app.observability import report_exception
from app.rate_limit import limiter
from app.tasks.scheduler import start_scheduler, stop_scheduler

_log_processors: list = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
]
if settings.debug:
    _log_processors.append(structlog.dev.ConsoleRenderer())
else:
    _log_processors.append(structlog.processors.JSONRenderer())

structlog.configure(processors=_log_processors)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Bootstrap admin user if none exists. Wrapped because the users table
    # may not exist yet on first run before migrations — log + continue.
    try:
        async with async_session() as db:
            await ensure_admin_user(db)
    except Exception as exc:
        logger.warning(
            "admin_bootstrap_failed",
            error=str(exc),
            hint="Run `make migrate` if the users table doesn't exist yet.",
        )

    logger.info("starting_scheduler")
    start_scheduler()
    yield
    logger.info("stopping_scheduler")
    stop_scheduler()


app = FastAPI(
    title="MyApp API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CSRFMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions. FastAPI still handles HTTPException
    and request-validation errors itself; this only fires for genuinely
    unexpected failures. We report via the observability seam and return a
    generic body so internal details (stack traces, DB errors) never leak to
    the client."""
    report_exception(exc, method=request.method, path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Outermost middleware — sees the final response (including CORS headers and
# rate-limit 429s) and binds a request_id that downstream structlog calls
# inherit via contextvars.
@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start = time.perf_counter()
    with structlog.contextvars.bound_contextvars(request_id=request_id):
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response


# Admin routes
app.include_router(auth.router)
app.include_router(items.router)
app.include_router(audit_log.router)
app.include_router(users.router)

# Public routes
app.include_router(public.router)


@app.get("/api/health")
async def health():
    """Readiness probe — verifies the app can actually serve traffic by
    round-tripping a trivial query to the database. Returns 503 if the DB is
    unreachable so a load balancer / orchestrator stops routing to this
    instance instead of letting requests fail. This is the endpoint the
    Docker HEALTHCHECK targets."""
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("health_check_db_unreachable", error=str(exc))
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    return {"status": "ok"}


@app.get("/api/health/live")
async def liveness():
    """Liveness probe — process is up and the event loop is responsive. Does
    not touch the database (a DB outage shouldn't cause the orchestrator to
    kill and restart an otherwise-healthy process). Use this for liveness and
    `/api/health` for readiness."""
    return {"status": "ok"}
