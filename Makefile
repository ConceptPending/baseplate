.PHONY: dev dev-backend dev-frontend db migrate lint install venv install-hooks generate-client stop restart verify-promotion check-portability spec-check spec-doc

# One canonical interpreter for every target. PY resolves to the backend venv if
# it exists, else the bootstrap Python ($(PYTHON)). $(abspath ...) keeps the path
# valid after a `cd backend`. Tools run as `$(PY) -m <tool>` so they work whether
# or not the venv is on your PATH, and avoid PATH ambiguity with a global
# executable from a different interpreter. Override either on the command line:
#   make test-backend PY=/path/to/python      make install PYTHON=python3.12
PYTHON ?= python3
VENV := backend/.venv
VENV_PY := $(abspath $(VENV)/bin/python)
ifeq ($(OS),Windows_NT)
VENV_PY := $(abspath $(VENV)/Scripts/python.exe)
endif
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(PYTHON))

# Start everything
dev:
	$(MAKE) -j3 db dev-backend dev-frontend

db:
	docker compose up -d postgres

dev-backend:
	cd backend && PYTHONPATH=. $(PY) -m uvicorn app.main:app --reload --port 8001

dev-frontend:
	cd frontend && npm run dev -- --port 3001

# Deterministic from a clean checkout: create backend/.venv if absent, then
# install backend deps (into that venv) + frontend deps. Uses $(VENV_PY)
# directly — not $(PY), which resolved before the venv existed — so a first-run
# install populates the freshly-created venv rather than an arbitrary
# interpreter. No more PEP 668 "externally-managed-environment" surprises.
install: venv
	cd backend && $(VENV_PY) -m pip install -e ".[dev]"
	cd frontend && npm install

# Create the backend virtualenv (idempotent) and upgrade its packaging tools.
venv:
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo "error: '$(PYTHON)' not found — install Python 3 or run 'make install PYTHON=/path/to/python3'"; \
		exit 1; }
	@test -x "$(VENV_PY)" || $(PYTHON) -m venv "$(VENV)"
	@"$(VENV_PY)" -m pip install --upgrade pip

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

# Validate the state-machine specs are well-formed (lifecycle recipe).
spec-check:
	cd backend && DEBUG=true PYTHONPATH=. $(PY) scripts/statespec.py check

# Regenerate docs/specs/*.md from the specs (committed; CI checks freshness).
spec-doc:
	cd backend && DEBUG=true PYTHONPATH=. $(PY) scripts/statespec.py render

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
