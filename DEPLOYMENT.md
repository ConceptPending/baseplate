# Deployment

The repo is deployed to Railway as a working demo:

- **Frontend**: https://frontend-production-7642.up.railway.app
- **Backend**: https://backend-production-dc23e.up.railway.app
- **Health**: `/api/health` on backend, `/healthz` on frontend

This document captures what it took to deploy the first time, including the
two issues hit and how they were resolved. If you're forking Baseplate to
your own Railway project, these notes save you from rediscovering them.

## Quick path (CLI-first)

Assumes Railway CLI 4.44+ installed and authenticated (`railway login`).

```bash
# 1. Create the project
railway init --name Baseplate

# 2. Add Postgres
railway add --database postgres

# 3. Create backend service. The CLI will prompt for variables interactively
#    — paste these in (replacing values), or skip and set via the dashboard.
railway add --service backend

# Backend env vars — DATABASE_URL uses Railway variable references so it
# tracks the Postgres credentials automatically:
railway variable set --service backend --skip-deploys \
  "DATABASE_URL=postgresql+asyncpg://\${{Postgres.PGUSER}}:\${{Postgres.PGPASSWORD}}@\${{Postgres.PGHOST}}:\${{Postgres.PGPORT}}/\${{Postgres.PGDATABASE}}" \
  "JWT_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  "ADMIN_EMAIL=you@example.com" \
  "ADMIN_PASSWORD_HASH=$(make hash-password)" \
  "COOKIE_SECURE=true" \
  "DEBUG=false" \
  "PORT=8001"

# 4. Create frontend service
railway add --service frontend --variables "API_URL=http://backend.railway.internal:8001"

# 5. First deploys (one shell per service to keep cwd clean)
railway up --service backend --ci          # from backend/ directory
railway up --service frontend --ci         # from frontend/ directory

# 6. Generate public domains
railway domain --service backend --port 8001
railway domain --service frontend --port 3001
```

The backend's CMD runs `alembic upgrade head` on startup, so migrations apply
automatically. The bootstrap admin is created from `ADMIN_EMAIL` +
`ADMIN_PASSWORD_HASH` the first time the app starts (see
`backend/app/bootstrap.py`).

## Wiring up GitHub Actions deploy (optional)

CI runs tests on every push/PR regardless. To **also** deploy automatically
when CI succeeds on `main`, configure three GitHub repo items:

| Type | Name | Value |
|---|---|---|
| Secret | `RAILWAY_TOKEN` | Account/workspace token from https://railway.com/account/tokens (**not** a project token) |
| Secret | `RAILWAY_PROJECT_ID` | Project UUID, visible in the Railway dashboard URL |
| Variable | `RAILWAY_DEPLOY_ENABLED` | `true` |

```bash
# Via gh CLI:
gh secret set RAILWAY_TOKEN --body "..."        # paste workspace token
gh secret set RAILWAY_PROJECT_ID --body "..."   # paste project UUID
gh variable set RAILWAY_DEPLOY_ENABLED --body "true"
```

Without the variable, the `deploy-railway.yml` workflow's jobs skip — so a
freshly cloned starter doesn't fail CI before Railway is set up.

## Issues hit on the first real deploy

These are the rough edges I ran into. They're not bugs in Baseplate, but
they cost time the first time around.

### 1. Railway's `$PORT` injection vs. Dockerfile defaults

**Symptom**: Backend's `/api/health` worked via the public domain but the
frontend's `/api/auth/login` returned 500. Logs showed
`ECONNREFUSED backend.railway.internal:8001`.

**Cause**: Railway injects `$PORT` as an environment variable per service.
My backend Dockerfile's `CMD` honored it (`--port ${PORT:-8001}`), so uvicorn
bound to Railway's injected port (e.g. 8080), not 8001. The frontend's
`API_URL` was hardcoded to port 8001. Internal-service-to-service traffic
needs the right port.

**Fix**: Explicitly set `PORT=8001` on the backend service to override
Railway's auto-injection. The frontend's `API_URL=http://backend.railway.internal:8001`
then works. Trade-off: less idiomatic for Railway but keeps Baseplate's
declared port (`8001`) consistent across local dev, Docker, and Railway.

**Alternative that didn't work**: Using Railway variable reference
`${{backend.PORT}}` in the frontend's `API_URL`. Railway's injected `$PORT`
isn't exposed as a user-visible variable, so the reference resolves to an
empty string. Document so the next person doesn't try it.

### 2. `railway up` in CI needs `--environment` explicitly

**Symptom**: The first auto-deploy from GitHub Actions failed instantly with
`No environment specified. Set RAILWAY_ENVIRONMENT_ID, use --environment, or
run 'railway environment' to link one.`

**Cause**: Locally, `railway link` writes a config file in the project's
`.railway/` directory that pins the environment. CI's ephemeral checkout has
no such file. The `RAILWAY_API_TOKEN` + `RAILWAY_PROJECT_ID` env vars tell
the CLI *which project*, but not *which environment* within it.

**Fix**: Add `--environment production` to the `railway up` commands in
`.github/workflows/deploy-railway.yml`. Hardcoding the name (not the UUID)
keeps the workflow portable across forks. Locally `railway up` still
defaults to the linked environment, so this only changes CI behavior.

### 3. `railway up` picks the wrong Dockerfile if you're in the wrong directory

**Symptom**: Ran `railway up --service frontend --ci` from the repo root. Got
a successful build... of the backend image, applied to the frontend service.

**Cause**: `railway up` deploys from the **current working directory**.
There's no `--dir` flag, no automatic detection of which Dockerfile to use
per service. The repo root has neither a `Dockerfile` nor a `package.json`,
so Railway makes a guess.

**Fix**: Always `cd` into the service's directory before `railway up`. The
GitHub Actions workflow does this via `defaults.run.working-directory:
{backend|frontend}` per job. For CLI use:

```bash
cd backend && railway up --service backend --ci
cd frontend && railway up --service frontend --ci
```

Or use `railway link --service <name>` from inside each directory to bind
the cwd to that service.

## DATABASE_URL format

Railway's Postgres plugin sets `DATABASE_URL=postgresql://...` (the standard
PG URL format). Baseplate's SQLAlchemy config expects
`postgresql+asyncpg://...` (driver-prefixed for the asyncpg driver).

Don't just reference `${{Postgres.DATABASE_URL}}` directly — the prefix
won't match. Compose the URL from the individual fields instead:

```
DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
```

That tracks the Postgres credentials automatically (if Railway rotates them,
the backend picks them up on next deploy) while keeping the asyncpg prefix.

## Portability contract & other platforms

Baseplate ships Railway-first but is **not Railway-coupled**. It depends only on
a small, platform-neutral contract, which CI verifies on every push via
`backend/scripts/check_portability.py`:

```bash
make check-portability
```

The check asserts both Dockerfiles read `$PORT`, run as a non-root user, and
declare an HTTP `HEALTHCHECK`; that config is env-driven; that Postgres is the
only required external service; and that migrations run on start. If any item
regresses, CI fails — so the "runs anywhere that honours the contract" claim
stays true as the code evolves.

### Per-platform conformance

| Platform | Status | What it needs |
|---|---|---|
| **Railway** | ✅ Verified (live demo) | Three services (backend, frontend, Postgres plugin); env vars per the Quick path; `PORT=8001` pinned on the backend (see issue 1 above). |
| **Render** | ⚠️ Contract-mapped, smoke-test pending | A `render.yaml` blueprint with two Docker web services + a managed Postgres. Render injects `$PORT` (both images honour it). Set the same env vars; compose `DATABASE_URL` with the `+asyncpg` prefix from Render's Postgres fields. Frontend `API_URL` → the backend service's internal URL. |
| **Fly.io** | ⚠️ Contract-mapped, smoke-test pending | A `fly.toml` per service (`fly launch` from `backend/` and `frontend/`). Fly sets `PORT` via `[env]`/`internal_port`; both images bind it. Attach Fly Postgres and set `DATABASE_URL` (asyncpg prefix). Use Fly private networking (`.internal`) for `API_URL`. |
| **Google Cloud Run** | ⚠️ Contract-mapped, smoke-test pending | Deploy each Dockerfile as a service (`gcloud run deploy --source`). Cloud Run injects `$PORT` (default 8080 — both images read it, so no change needed). Use Cloud SQL for Postgres; set env vars via `--set-env-vars` / Secret Manager. |
| **AWS App Runner / ECS Fargate** | ⚠️ Contract-mapped, smoke-test pending | Push both images to ECR; App Runner/ECS sets the port (App Runner defaults 8080 — honoured). RDS Postgres; env vars via the service config / Secrets Manager. Run as the non-root user the images already declare. |
| **Kubernetes** | ⚠️ Contract-mapped, smoke-test pending | Two Deployments + Services; set `PORT` via container env; wire `livenessProbe`/`readinessProbe` to the healthcheck paths; a managed or in-cluster Postgres; secrets via `Secret` objects. |

"Contract-mapped" means the portability check passes and the platform provides
everything the contract requires — but no live deployment has been smoke-tested
there yet. Treat the first deploy as the verification step. **To make one
first-class**: add a `deploy-<platform>.yml` mirroring `deploy-railway.yml`'s
`workflow_run` gate, smoke-test it, and move its row to ✅.

## What's still untested

- Auto-deploy via GitHub Actions. CLI-first deploy works; the CI path is
  configured (secrets + variable set) and the workflow itself was validated
  on previous PRs in skip-mode. The first real push to `main` after wiring
  Railway will exercise it for the first time.
- Long-term: log volume, container restart behavior under load, custom
  domain attachment, database backups. The demo is a single instance with
  Railway-managed Postgres on the free tier.

## Resetting / re-deploying

To redeploy after a config change without pushing code:

```bash
railway redeploy --service backend --yes
railway redeploy --service frontend --yes
```

To wipe and start over: in the Railway dashboard, **Project → Settings →
Danger → Delete Project**. The CLI doesn't expose a project-delete command.
