# Claude / LLM agent notes

Full-stack starter: FastAPI + Next.js 16 + PostgreSQL. `README.md` is the source of truth for stack overview and quick start — read it if you're new to this repo.

## Dev commands

```bash
make dev                          # Postgres + backend (:8001) + frontend (:3001)
make test-backend                 # pytest — uses SQLite via aiosqlite, no Postgres needed
make test-frontend                # vitest run
make lint                         # ruff (backend) + tsc --noEmit (frontend)
make migrate                      # alembic upgrade head
make migrate-new msg="add foo"    # autogenerate a new migration
make hash-password                # bcrypt hash for ADMIN_PASSWORD_HASH
make install-hooks                # one-time: register pre-commit hooks
make generate-client              # regenerate frontend types from backend OpenAPI
make stop                         # kill dev servers + Docker
```

## Conventions to follow

**Backend**

- Routes (`app/api/`) are thin: validate input, call a service, return. No DB queries inline.
- DB logic lives in `app/services/` as static methods on a `*Service` class.
- All models inherit `Base, TimestampMixin` and use `uuid_pk()` for primary keys.
- Response schemas use `model_config = {"from_attributes": True}` so SQLAlchemy models serialize directly.
- Register each new model in `app/models/__init__.py` — Alembic autogenerate reads `Base.metadata` from there.
- After adding or changing any Pydantic schema, run `make generate-client` so the frontend's `lib/api-types.ts` stays in sync. Drift is detectable by `tsc` failures later, but regen-on-change keeps the commit clean.

**Frontend**

- Route groups: `(public)/` gets header + footer (`app/(public)/layout.tsx`); `admin/` gets sidebar + auth (`app/admin/layout.tsx`).
- All API calls go through `lib/api.ts` (`fetchAPI<T>()` wrapper). Always pass `credentials: "include"` for authed endpoints.
- Request and response types come from `lib/api-types.ts` (auto-generated from the backend OpenAPI spec — don't edit by hand). `lib/types.ts` re-exports them with friendly names; add a new line there when you need to reference a backend schema from frontend code.
- Server components fetch via `API_BASE` from `lib/server-config.ts`. Client components use `lib/api.ts`.
- Browser never hits the backend directly — Next.js rewrites `/api/*` in `next.config.ts`.

## Adding a new domain model

`README.md` has a 10-step recipe under "Adding a new domain model". Follow it literally — model → register → migrate → schemas → service → routes → router include → TS type → API client → pages. The existing `Item` slice is the canonical reference.

## Lifecycle entities (state-machine specs)

This branch demonstrates the [`lifecycle-state-machine`](docs/recipes/lifecycle-state-machine.md) recipe. When an entity has a *lifecycle* — a `status` that moves through reviewable steps with rules about who may move it and when — model it as a declarative spec instead of a free-form `status` setter. The `Submission` slice is the reference here.

- The spec lives in `app/statespec/<entity>_spec.py`: states, named transitions (each with permitted **roles** and an optional **guard**), and invariants. Plain data — the single source of truth.
- The generic engine (`app/statespec/core.py`) is the **only** place a transition happens. The service calls `statespec.apply(SPEC, action, current_state, actor_roles, snapshot)` and persists the result — no `status = new_value` anywhere else.
- Roles are real and per-user: `User.roles` (a CSV column, vocabulary in `app/roles.py`); `deps.roles_for(user)` returns `user.role_set`. `is_admin` gates the admin area; `roles` gate which transitions an admin may fire. Assign via `PUT /api/admin/users/{id}/roles` (rejects unknown roles and removing the last holder of a role).
- **System-fired transitions**: an edge whose only role is `roles.SYSTEM` can be fired only by a scheduled job passing `frozenset({SYSTEM})` (see `SubmissionService.expire_stale`, wired in `app/tasks/scheduler.py`), never by a person. `SYSTEM` is in `ALL_ROLES` but not `HUMAN_ROLES`, so the assignment endpoint refuses it.
- **Verification is the point.** `tests/test_submission_statespec.py` is a Hypothesis `RuleBasedStateMachine` that asserts the spec's invariants hold over random sequences. Register new specs in `SPECS` (`scripts/statespec.py`) so `make spec-check` (CI gate) validates them and `make spec-doc` renders `docs/specs/<entity>-lifecycle.md` (generated; CI fails if stale).
- Not everything is a state machine. Plain CRUD (the `Item` slice) gets no spec.

## Gotchas

- **Ports**: backend `:8001`, frontend `:3001` — consistent across `Makefile` dev and both Dockerfiles. Railway injects `$PORT` at runtime, which the apps respect.
- **Startup validation**: when `DEBUG=false`, the backend refuses to boot with default `JWT_SECRET`, empty `ADMIN_PASSWORD_HASH`, or default `DATABASE_URL` (`app/config.py:28-39`). Use `DEBUG=true` locally if you're skipping `.env` setup.
- **Cookies require HTTPS in prod** (`COOKIE_SECURE=true`). Set `COOKIE_SECURE=false` for local HTTP dev.
- **Health endpoints**: `/api/health` is readiness (does a `SELECT 1`, returns 503 if the DB is down — the Docker HEALTHCHECK target); `/api/health/live` is liveness (no DB). When you add a dependency the app can't run without, consider adding it to the readiness check.
- **Unhandled exceptions** go through `app/main.py`'s catch-all handler → `app/observability.py:report_exception` → generic 500 (no stack leak). Wire Sentry/etc. inside `report_exception`, not at call sites. Frontend mirror: `lib/observability.ts:reportError`, used by the error boundaries and `lib/api.ts` (5xx/network only).
- **Security headers** live in `frontend/next.config.ts` `headers()` (CSP, HSTS, frame/nosniff/referrer/permissions). If you add an external script/style/image origin, widen the matching CSP directive there or it'll be blocked.
- **DB pool** is configured in `app/database.py` from `DB_POOL_*` settings; the sizing args are skipped for the SQLite test engine (guarded on the URL scheme).
- **`/docs` and `/redoc`** are disabled when `DEBUG=false`. Enable with `DEBUG=true`.
- **Backend tests use SQLite via aiosqlite** (`tests/conftest.py:14`). Don't add Postgres-specific SQL to models without verifying the migration still runs under SQLite — or update conftest to use Postgres.
- **Test auth helper**: `tests/test_items.py:4` `_login()` — copy this pattern in new test files that hit admin endpoints.
- **Vitest uses happy-dom** (not jsdom) for the DOM environment. Component tests with `@testing-library/react` work — see `__tests__/Button.test.tsx` for a template. Cleanup is registered in `__tests__/setup.ts`.

## Patterns to avoid

When you see these in the codebase, fix them rather than copy:

- `catch (err: any)` — use `unknown` plus a narrow check (`err instanceof Error`).
- `.catch(() => {})` swallowing API errors silently — surface the error to the user or at least `console.error`.

## Before declaring a task done

1. `make lint` — must pass.
2. `make test-backend` and `make test-frontend` — must pass.
3. Touched a model? Run `make migrate-new msg="..."` and read the generated migration before accepting it. Autogenerate is a starting point, not a verdict.
4. Touched a UI route? Start `make dev` and visit it. Type-checks aren't enough — verify the page renders and the API call succeeds.

## Auth model

- Users live in the `users` table (`app/models/user.py`). Login is by email + password (bcrypt).
- `ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH` env vars seed the **first** admin user on startup via `app/bootstrap.py:ensure_admin_user` (idempotent; only runs when no admin exists in the DB). After that, env vars are unused — manage users via the database.
- JWT cookie carries `sub = str(user.id)` (UUID), not the email. Renaming a user doesn't invalidate sessions.
- `deps.get_current_admin` returns a `User` model. Routes that only need the gate use `dependencies=[Depends(get_current_admin)]` on the router; routes that need the User object accept it as a parameter (see `auth.me`).
- **Roles vs. admin.** `is_admin` is the coarse gate (reach the admin area at all); `User.roles` (CSV; vocabulary in `app/roles.py`) is the fine-grained layer — which lifecycle actions an admin may perform. An admin can hold zero roles. The bootstrap admin is seeded with every human role; grant others deliberately via `PUT /api/admin/users/{id}/roles`. See "Lifecycle entities".

## CSRF protection

- `CSRFMiddleware` (`app/middleware/csrf.py`) enforces a double-submit token on every write (POST/PUT/PATCH/DELETE) that isn't on an exempt path. Login and `GET /api/auth/csrf` are the only exemptions.
- The backend issues a `csrf_token` cookie (non-HttpOnly, JS-readable) on login and via `GET /api/auth/csrf`.
- The frontend's `fetchAPI` wrapper (`lib/api.ts`) reads the cookie via `lib/csrf.ts:getCSRFToken()` and auto-attaches `X-CSRF-Token` on writes. Don't bypass `fetchAPI` for writes — calling `fetch()` directly will get 403'd.
- Token check uses `secrets.compare_digest` (constant-time).
- When testing writes, log in first and pass the returned csrf token in the header (`tests/test_items.py:_login` is the canonical pattern).
