# Framework

A production-ready full-stack starter. Clone it, rename "Item" to your domain model, and start building.

## Stack

| Layer      | Technology                                                        |
|------------|-------------------------------------------------------------------|
| Backend    | FastAPI, SQLAlchemy 2 (async), Pydantic v2, Alembic, APScheduler |
| Frontend   | Next.js 16, React 19, Tailwind CSS 4, TypeScript                 |
| Database   | PostgreSQL 16 (asyncpg driver)                                   |
| Auth       | JWT in httpOnly cookies, bcrypt password hashing                 |
| Testing    | pytest + pytest-asyncio (backend), Vitest + Testing Library (frontend) |
| Deploy     | Docker multi-stage builds, Railway via GitHub Actions            |
| Logging    | structlog (structured JSON in prod, colored console in dev)      |

## Quick start

```bash
cp .env.example backend/.env
cp .env.example frontend/.env.local  # only the API_URL line

make install         # pip install backend deps + npm install frontend deps
make db              # start Postgres 16 via Docker on port 5433
make migrate         # run Alembic migrations
make hash-password   # generate a bcrypt hash, paste into backend/.env as ADMIN_PASSWORD_HASH
make dev             # backend on :8001, frontend on :3001
```

Open `http://localhost:3001/admin/login` and log in with the username/password you configured.

## Project structure

```
├── backend/
│   ├── app/
│   │   ├── config.py           # Pydantic Settings (env vars)
│   │   ├── database.py         # async engine + session factory
│   │   ├── deps.py             # FastAPI dependencies (auth)
│   │   ├── main.py             # App factory, middleware, routers
│   │   ├── models/
│   │   │   ├── base.py         # DeclarativeBase, TimestampMixin, uuid_pk()
│   │   │   └── item.py         # Example model
│   │   ├── schemas/
│   │   │   ├── auth.py         # LoginRequest / LoginResponse
│   │   │   └── item.py         # ItemCreate / ItemUpdate / ItemResponse
│   │   ├── api/
│   │   │   ├── auth.py         # POST /login, /logout, GET /me
│   │   │   ├── items.py        # Admin CRUD (GET/POST/PATCH/DELETE)
│   │   │   └── public.py       # Public read endpoints
│   │   ├── services/
│   │   │   └── items.py        # DB query logic, separate from routes
│   │   └── tasks/
│   │       └── scheduler.py    # APScheduler with placeholder job
│   ├── alembic/                # Migration config + versions
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/                # Next.js App Router pages
│   │   │   ├── (public)/       # Public route group (Header + Footer)
│   │   │   └── admin/          # Admin route group (Sidebar)
│   │   ├── components/
│   │   │   ├── ui/             # Button, Card, Input, Modal, StatusPill
│   │   │   └── layout/         # Header, Footer
│   │   ├── lib/
│   │   │   ├── api.ts          # fetchAPI wrapper + typed endpoint functions
│   │   │   ├── auth.ts         # useRequireAuth() hook
│   │   │   ├── types.ts        # TypeScript interfaces
│   │   │   ├── constants.ts    # Site name, description
│   │   │   └── server-config.ts # Server-side API_BASE from env
│   │   └── middleware.ts       # Redirects unauthenticated /admin/* to /login
│   └── package.json
├── docker-compose.yml          # Local Postgres
├── Makefile                    # All dev/test/deploy commands
└── .github/workflows/deploy.yml
```

## Environment variables

### Backend (`backend/.env`)

| Variable              | Required | Default                                              | Description                            |
|-----------------------|----------|------------------------------------------------------|----------------------------------------|
| `DATABASE_URL`        | Yes      | `postgresql+asyncpg://myapp:myapp@localhost:5433/myapp` | Async PostgreSQL connection string  |
| `ADMIN_USERNAME`      | Yes      | `admin`                                              | Login username                         |
| `ADMIN_PASSWORD_HASH` | Yes      | —                                                    | bcrypt hash (generate with `make hash-password`) |
| `JWT_SECRET`          | Yes      | —                                                    | Random string for signing tokens       |
| `JWT_ALGORITHM`       | No       | `HS256`                                              | JWT signing algorithm                  |
| `JWT_EXPIRE_MINUTES`  | No       | `1440`                                               | Token lifetime (default 24h)           |
| `COOKIE_SECURE`       | No       | `true`                                               | Set `false` for local HTTP dev         |
| `CORS_ORIGINS`        | No       | `["http://localhost:3001"]`                          | Allowed CORS origins (JSON list)       |
| `DEBUG`               | No       | `false`                                              | Enables `/docs` and `/redoc`, disables startup validation |

### Frontend (`frontend/.env.local`)

| Variable   | Required | Default                  | Description                  |
|------------|----------|--------------------------|------------------------------|
| `API_URL`  | Yes      | `http://localhost:8001`  | Backend URL for API proxying |

### Startup validation

When `DEBUG=false` (the default), the backend will refuse to start if:
- `JWT_SECRET` is the default placeholder or empty
- `ADMIN_PASSWORD_HASH` is empty
- `DATABASE_URL` uses default local credentials

This prevents deploying with insecure defaults. Set `DEBUG=true` locally to skip these checks, or set real values.

## Architecture

### How requests flow

```
Browser → Next.js (:3001) → rewrites /api/* → FastAPI (:8001) → PostgreSQL
```

The Next.js `next.config.ts` proxies all `/api/*` requests to the backend. The browser only talks to the frontend server. In production on Railway, each service gets its own URL and the same rewrite proxy applies — the frontend's `API_URL` env var points to the backend's internal Railway URL.

### Authentication

1. User submits credentials to `POST /api/auth/login`
2. Backend verifies against bcrypt hash, issues a JWT, sets it as an httpOnly cookie
3. All subsequent requests include the cookie automatically
4. `middleware.ts` on the frontend checks for the cookie and redirects to `/admin/login` if missing
5. `useRequireAuth()` hook validates the token server-side via `GET /api/auth/me`
6. Admin API routes use `Depends(get_current_admin)` which extracts and verifies the JWT from the cookie

### Backend patterns

**Models** inherit from `Base` and `TimestampMixin`. Use `uuid_pk()` for UUID primary keys with auto-generation:

```python
class Item(Base, TimestampMixin):
    __tablename__ = "items"
    id = uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
```

**Services** contain all database query logic. Routes stay thin — they validate input, call a service method, and return the result:

```python
@router.post("", response_model=ItemResponse, status_code=201)
async def create_item(data: ItemCreate, admin=Depends(get_current_admin), db=Depends(get_db)):
    return await ItemService.create(db, data)
```

**Schemas** use Pydantic v2 with `model_config = {"from_attributes": True}` so SQLAlchemy models serialize directly.

### Frontend patterns

**API client** (`lib/api.ts`): A single `fetchAPI<T>()` wrapper handles JSON headers, error extraction, and 204 responses. All endpoint functions are typed and use `credentials: "include"` for cookie auth.

**Route groups**: `(public)/` has the Header + Footer layout. `admin/` has the sidebar layout. This separation means public pages and admin pages can have completely different chrome.

**Server components** fetch data at the edge. Client components (`"use client"`) handle interactivity. The admin pages are client components because they need auth state and user interaction.

## Make commands

| Command                      | What it does                                    |
|------------------------------|-------------------------------------------------|
| `make dev`                   | Starts Postgres + backend + frontend in parallel |
| `make dev-backend`           | Backend only on :8001                           |
| `make dev-frontend`          | Frontend only on :3001                          |
| `make db`                    | Start Postgres container on port 5433           |
| `make install`               | `pip install -e ".[dev]"` + `npm install`       |
| `make migrate`               | `alembic upgrade head`                          |
| `make migrate-new msg="..."` | Generate a new auto-detected migration          |
| `make test-backend`          | `pytest -v`                                     |
| `make test-frontend`         | `vitest run`                                    |
| `make lint`                  | Python compile check + Next.js ESLint           |
| `make hash-password`         | Interactive bcrypt hash generator                |
| `make stop`                  | Kill dev servers + stop Docker                  |
| `make restart`               | Stop then start everything                      |

## Extending the framework

### Adding a new domain model

This is the most common operation. Replace "Item" or add alongside it.

1. **Create the model** in `backend/app/models/`:
   ```python
   # backend/app/models/widget.py
   from sqlalchemy import String, Integer
   from sqlalchemy.orm import Mapped, mapped_column
   from app.models.base import Base, TimestampMixin, uuid_pk

   class Widget(Base, TimestampMixin):
       __tablename__ = "widgets"
       id = uuid_pk()
       title: Mapped[str] = mapped_column(String(255))
       count: Mapped[int] = mapped_column(Integer, default=0)
   ```

2. **Register the model** in `backend/app/models/__init__.py`:
   ```python
   from app.models.widget import Widget
   ```
   Alembic's `env.py` imports `Base` from here, so any model that inherits `Base` is auto-detected.

3. **Generate the migration**:
   ```bash
   make migrate-new msg="add widgets table"
   make migrate
   ```

4. **Add schemas** in `backend/app/schemas/widget.py`:
   ```python
   from pydantic import BaseModel
   from uuid import UUID
   from datetime import datetime

   class WidgetCreate(BaseModel):
       title: str
       count: int = 0

   class WidgetResponse(BaseModel):
       id: UUID
       title: str
       count: int
       created_at: datetime
       updated_at: datetime
       model_config = {"from_attributes": True}
   ```

5. **Add a service** in `backend/app/services/widget.py` — follow the `ItemService` pattern.

6. **Add routes** in `backend/app/api/widget.py` — follow the `items.py` pattern for admin routes, `public.py` for public routes.

7. **Register the router** in `backend/app/main.py`:
   ```python
   from app.api import widget
   app.include_router(widget.router)
   ```

8. **Add the TypeScript type** in `frontend/src/lib/types.ts`:
   ```typescript
   export interface Widget {
     id: string;
     title: string;
     count: number;
     created_at: string;
     updated_at: string;
   }
   ```

9. **Add API functions** in `frontend/src/lib/api.ts` — follow the Item functions pattern.

10. **Add pages** — copy `admin/items/page.tsx` as a starting point for the admin UI, and `(public)/items/page.tsx` for the public view.

### Adding a background job

Edit `backend/app/tasks/scheduler.py`:

```python
async def my_job():
    async with async_session() as db:
        # your logic here
        pass

def start_scheduler():
    scheduler.add_job(my_job, IntervalTrigger(minutes=15), id="my_job", replace_existing=True)
    scheduler.start()
```

Import `async_session` from `app.database` to get a database session inside jobs — don't use FastAPI's `Depends` outside of request handlers.

### Adding a new UI component

Components live in `frontend/src/components/ui/`. The design system uses CSS custom properties defined in `globals.css`:

- `bg-background` / `text-foreground` — page-level colors
- `bg-surface` / `bg-surface-elevated` — card and panel backgrounds
- `text-muted` — secondary text
- `border-border` — borders
- `bg-accent` / `bg-accent-bright` — primary action color (indigo by default)

Dark mode is available by adding the `dark` class to `<html>`. The CSS variables swap automatically.

### Adding a public-facing route

1. Create `frontend/src/app/(public)/your-page/page.tsx`
2. It automatically inherits the Header + Footer layout from `(public)/layout.tsx`
3. For server-rendered data, fetch from the backend using `API_BASE` from `lib/server-config.ts`:
   ```typescript
   const res = await fetch(`${API_BASE}/api/public/your-endpoint`, { next: { revalidate: 60 } });
   ```

### Adding an admin page

1. Create `frontend/src/app/admin/your-page/page.tsx`
2. It automatically gets the sidebar layout and is protected by `middleware.ts`
3. Add the nav link in `frontend/src/app/admin/layout.tsx`

## Deployment to Railway

### First-time setup

1. Create a Railway project with three services: `backend`, `frontend`, and a PostgreSQL plugin
2. Set environment variables on each Railway service:
   - **backend**: `DATABASE_URL` (from Postgres plugin), `JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `COOKIE_SECURE=true`, `CORS_ORIGINS=["https://your-frontend.up.railway.app"]`
   - **frontend**: `API_URL` (internal Railway URL of the backend, e.g. `http://backend.railway.internal:8001`)
3. Add two secrets to your GitHub repo:
   - **`RAILWAY_TOKEN`** — a **workspace/account token** (Railway → Account
     Settings → Tokens). *Not* a per-project token. The workflow feeds it to the
     CLI as `RAILWAY_API_TOKEN`; a project token in this slot fails with
     `Invalid RAILWAY_TOKEN`. One account token covers the whole project.
   - **`RAILWAY_PROJECT_ID`** — the project's ID (Railway project → Settings).
4. Push to `main` — GitHub Actions runs the tests, then deploys both services.

### How the deploy works

The `.github/workflows/deploy.yml` workflow (`CI & Deploy`):
- On every push **and pull request**, runs `test-backend` (ruff + pytest) and
  `test-frontend` (typecheck, vitest, build).
- `deploy-backend` / `deploy-frontend` `needs` both test jobs and run **only on
  pushes to `main`** — so a red test run, or any PR, never deploys.
- Deploy uses `railway up --service <name>`, which builds each service's
  Dockerfile on Railway's infrastructure.

### Railway environment notes

- Railway provides `DATABASE_URL` in the standard `postgresql://` format. The backend config expects `postgresql+asyncpg://` — you may need to adjust the variable or add a prefix in Railway's variable references.
- The backend Dockerfile exposes port 8001 via `uvicorn`. Railway auto-detects the port.
- The frontend Dockerfile runs `next start` on port 3000. Set `PORT=3000` in Railway if it doesn't auto-detect.
- Run `make migrate` manually after the first deploy, or add a Railway deploy hook / release command.

## Testing

### Backend

Tests use SQLite (via aiosqlite) instead of PostgreSQL so they run without Docker. The `conftest.py` sets up an in-memory test database, overrides FastAPI's `get_db` dependency, and generates a real bcrypt hash for auth tests.

```bash
make test-backend       # runs pytest -v
```

To add tests, create files in `backend/tests/test_*.py`. The `client` fixture gives you an authenticated-capable `httpx.AsyncClient`:

```python
@pytest.mark.asyncio
async def test_my_endpoint(client):
    await _login(client)  # sets auth cookie
    response = await client.get("/api/admin/widgets")
    assert response.status_code == 200
```

### Frontend

Tests use Vitest with jsdom and Testing Library. The setup file is at `src/__tests__/setup.ts`.

```bash
make test-frontend      # runs vitest run
```

## Gotchas and things to know

- **`/docs` is disabled in production.** Set `DEBUG=true` to enable the Swagger UI at `/docs` and ReDoc at `/redoc`. This is controlled in `main.py`.
- **Rate limiting** is set to 60 requests/minute globally via SlowAPI. Adjust in `main.py`. Add per-endpoint limits with `@limiter.limit("10/minute")` on individual route handlers.
- **The middleware.ts deprecation warning** — Next.js 16 is renaming the `middleware.ts` convention to `proxy.ts`. The current file still works but you'll see a build warning. Rename when ready.
- **UUID primary keys** — all models use UUID v4 via PostgreSQL's native UUID type. The `uuid_pk()` helper in `models/base.py` handles this.
- **`from_attributes = True`** on response schemas means you return SQLAlchemy model instances directly from routes — Pydantic serializes them automatically.
- **The frontend proxies `/api/*`** to the backend via Next.js rewrites in `next.config.ts`. The browser never talks to the backend directly. This avoids CORS issues and keeps the backend URL private.
- **Cookies require HTTPS in production.** `COOKIE_SECURE=true` (the default) means auth cookies won't be sent over plain HTTP. This is correct for production. Set `false` for local dev without HTTPS.
