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
make stop                         # kill dev servers + Docker
```

## Conventions to follow

**Backend**

- Routes (`app/api/`) are thin: validate input, call a service, return. No DB queries inline.
- DB logic lives in `app/services/` as static methods on a `*Service` class.
- All models inherit `Base, TimestampMixin` and use `uuid_pk()` for primary keys.
- Response schemas use `model_config = {"from_attributes": True}` so SQLAlchemy models serialize directly.
- Register each new model in `app/models/__init__.py` — Alembic autogenerate reads `Base.metadata` from there.

**Frontend**

- Route groups: `(public)/` gets header + footer (`app/(public)/layout.tsx`); `admin/` gets sidebar + auth (`app/admin/layout.tsx`).
- All API calls go through `lib/api.ts` (`fetchAPI<T>()` wrapper). Always pass `credentials: "include"` for authed endpoints.
- Server components fetch via `API_BASE` from `lib/server-config.ts`. Client components use `lib/api.ts`.
- Browser never hits the backend directly — Next.js rewrites `/api/*` in `next.config.ts`.

## Adding a new domain model

`README.md` has a 10-step recipe under "Adding a new domain model". Follow it literally — model → register → migrate → schemas → service → routes → router include → TS type → API client → pages. The existing `Item` slice is the canonical reference.

## Gotchas

- **Ports**: backend `:8001`, frontend `:3001` — consistent across `Makefile` dev and both Dockerfiles. Railway injects `$PORT` at runtime, which the apps respect.
- **Startup validation**: when `DEBUG=false`, the backend refuses to boot with default `JWT_SECRET`, empty `ADMIN_PASSWORD_HASH`, or default `DATABASE_URL` (`app/config.py:28-39`). Use `DEBUG=true` locally if you're skipping `.env` setup.
- **Cookies require HTTPS in prod** (`COOKIE_SECURE=true`). Set `COOKIE_SECURE=false` for local HTTP dev.
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

## Planned changes (don't design around current state)

These are scheduled. When scoping new work, prefer designs that survive the migration:

- **Users table replacing single-admin auth** — today auth uses one `ADMIN_USERNAME` + `ADMIN_PASSWORD_HASH` env pair. A `users` table is planned; `deps.get_current_admin` will return a `User` model instead of a string. Don't build features that assume only one admin exists.
- **CSRF protection (double-submit token)** — today cookie auth relies on `SameSite=lax`. A token-based CSRF defense is planned. New write endpoints should land normally; the middleware will layer on top.
