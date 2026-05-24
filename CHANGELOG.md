# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- **Renamed project from Framework to Baseplate.** The repo is now `ConceptPending/baseplate` (old URLs redirect). Doc references updated throughout. Python `app/` package and example "MyApp" placeholders unchanged — those represent the user's app, not Baseplate itself.
- **README rewritten** to lead with concrete use cases ("Directory or data product", "Internal operations dashboard", "Intake + review queue", "AI workflow with human-in-the-loop", "Niche structured CMS", "Scheduled monitor") and named personas (solo founders, consultants, domain experts with technical help, internal tools engineers, founders validating non-SaaS products). Adds explicit "Who this is *not* for" qualifiers. New "What if my app grows into a SaaS?" section pointing at the growth-path doc. New "Portability contract" table documenting the Docker contract.

### Added
- `docs/growth-paths/multi-tenant.md` — step-by-step migration guide for evolving Baseplate from single-tenant → multi-org → SaaS. Names the architectural seams already in place (service layer, centralised auth context, alembic migrations), what to add at each stage, what to test for tenant isolation, and which migration anti-patterns to avoid.

### Added
- Live demo deployment on Railway (frontend, backend, Postgres). README links to the public URL.
- `DEPLOYMENT.md` with end-to-end CLI deploy steps, GitHub Actions wiring instructions, and a "Issues hit" section documenting the three real footguns (`$PORT` injection, missing `--environment` in CI, `railway up` cwd dependency).

### Fixed
- `deploy-railway.yml`: pass `--environment production` to `railway up`. Without it the CLI errors with "No environment specified" in CI (no `.railway/` link dir).

## [0.1.0] — 2026-05-24

Initial public release.

### Added

**Backend** — FastAPI 0.115+ with SQLAlchemy 2 async, Pydantic v2, Alembic
migrations, and an example `Item` CRUD slice (model → migration → service →
routes). Structured logging via structlog with `X-Request-ID` propagation,
per-endpoint rate limiting via SlowAPI (5/min on `/api/auth/login`, 60/min
default), and a background scheduler scaffold via APScheduler.

**Authentication** — `users` table (`email`, `password_hash`, `is_admin`),
email-based login with bcrypt verification, JWT in `HttpOnly` + `SameSite=Lax`
cookies (JWT `sub = user.id` UUID so renames don't invalidate sessions).
Idempotent admin bootstrap from `ADMIN_EMAIL` + `ADMIN_PASSWORD_HASH` on first
startup. Startup validation refuses to boot with default or short (<32 byte)
JWT secrets. Identical responses for wrong-password vs unknown-user (no
enumeration via timing or error messages).

**CSRF protection** — Double-submit cookie middleware on all non-safe,
non-exempt writes. Token issued on login and via `GET /api/auth/csrf`. Frontend
`fetchAPI` auto-attaches the `X-CSRF-Token` header.

**Frontend** — Next.js 16 App Router with `(public)` and `admin` route groups,
React 19, Tailwind CSS 4, TypeScript strict mode. Shared UI components
(`Button`, `Card`, `Input`, `Modal`, `StatusPill`, `ErrorBanner`) with
CSS-variable theming for light/dark mode. Typed API client. `useRequireAuth`
hook plus Next.js middleware for unauthenticated redirects.

**Infrastructure** — Multi-stage backend Dockerfile (build tools stripped from
runtime), non-root containers (uid 1000 in both images), `HEALTHCHECK`
directives, `/healthz` route on the frontend. Alembic migrations run on
container start; no manual step.

**CI/CD** — Platform-agnostic `ci.yml` (lint + tests + build, runs on every
push/PR). Opt-in `deploy-railway.yml` triggered via `workflow_run` after CI
success, gated on `vars.RAILWAY_DEPLOY_ENABLED == 'true'` so a fresh clone
doesn't fail CI before Railway is set up. Dependabot weekly with majors split
from grouped minor/patch updates.

**Tests** — 21 backend tests (pytest + aiosqlite — no Postgres required), 8
frontend tests (vitest + happy-dom + Testing Library). All gated by CI.

**Developer experience** — `make dev` brings up Postgres + backend (:8001) +
frontend (:3001) in parallel. Pre-commit hooks (ruff check + ruff format + tsc
+ ESLint + standard housekeeping). `make hash-password` for bcrypt generation.
Single-command tests, single-command lint.

**LLM-friendly docs** — [`CLAUDE.md`](CLAUDE.md) documents conventions, dev
commands, gotchas, anti-patterns to fix when seen, and a definition-of-done
checklist. [`.github/copilot-instructions.md`](.github/copilot-instructions.md)
mirrors it for non-Claude harnesses. README includes a 10-step recipe for
adding new domain models, plus full architecture overview.

**Repository hygiene** — MIT licensed, `.env.example` files tracked at three
levels, `CONTRIBUTING.md`, `SECURITY.md`, GitHub PR template, README badges.

[Unreleased]: https://github.com/ConceptPending/baseplate/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ConceptPending/baseplate/releases/tag/v0.1.0
