.PHONY: dev dev-backend dev-frontend db migrate lint install install-hooks generate-client stop restart verify-promotion check-portability

# Prefer the backend virtualenv if it exists, else fall back to whatever
# `python` is on PATH (e.g. an already-activated venv). Tools are invoked as
# `$(PY) -m <tool>` so they run whether or not the venv is on your PATH — no
# more "pytest: command not found" / "python: command not found" if you forgot
# to activate. $(abspath ...) keeps the path valid after a `cd backend`.
VENV_PY := $(abspath backend/.venv/bin/python)
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),python)

# Start everything
dev:
	$(MAKE) -j3 db dev-backend dev-frontend

db:
	docker compose up -d postgres

dev-backend:
	cd backend && PYTHONPATH=. $(PY) -m uvicorn app.main:app --reload --port 8001

dev-frontend:
	cd frontend && npm run dev -- --port 3001

install:
	cd backend && $(PY) -m pip install -e ".[dev]"
	cd frontend && npm install

install-hooks:
	pre-commit install

# Regenerate frontend TypeScript types from the FastAPI OpenAPI spec.
# Run after changes to backend Pydantic schemas. The output file is
# committed so LLMs and tests can rely on it without running the
# generator. CI doesn't run this — drift gets caught at next manual
# regen + the resulting tsc errors.
generate-client:
	cd backend && DEBUG=true PYTHONPATH=. $(PY) scripts/dump_openapi.py > /tmp/baseplate-openapi.json
	cd frontend && npx openapi-typescript /tmp/baseplate-openapi.json -o src/lib/api-types.ts
	rm -f /tmp/baseplate-openapi.json

migrate:
	cd backend && PYTHONPATH=. $(PY) -m alembic upgrade head

migrate-new:
	cd backend && PYTHONPATH=. $(PY) -m alembic revision --autogenerate -m "$(msg)"

lint:
	cd backend && $(PY) -m ruff check app/ tests/
	cd frontend && npx tsc --noEmit
	cd frontend && npm run lint

test-backend:
	cd backend && PYTHONPATH=. $(PY) -m pytest -v

test-frontend:
	cd frontend && npx vitest run

# Stop all services
stop:
	-pkill -f "uvicorn app.main:app" 2>/dev/null
	-pkill -f "next dev.*--port 3001" 2>/dev/null
	docker compose down

# Restart everything
restart: stop
	sleep 1
	$(MAKE) dev

hash-password:
	@$(PY) -c "import bcrypt, getpass; print(bcrypt.hashpw(getpass.getpass('Password: ').encode(), bcrypt.gensalt()).decode())"

# Verify this project honours the Flatpack it was promoted from.
# Expects reference/original-flatpack.html in the project root.
# See docs/promoting-a-flatpack.md.
verify-promotion:
	cd backend && DEBUG=true PYTHONPATH=. $(PY) scripts/verify_promotion.py ../reference/original-flatpack.html

# Mechanically assert the deployment portability contract (Dockerfiles read
# $PORT, run non-root, declare healthchecks; config is env-driven; migrations
# run on start). See DEPLOYMENT.md "Portability contract".
check-portability:
	$(PY) backend/scripts/check_portability.py
