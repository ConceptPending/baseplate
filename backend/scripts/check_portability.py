#!/usr/bin/env python3
"""Mechanically verify Baseplate's portability contract.

The README claims Baseplate "runs unchanged on Render, Fly.io, Google Cloud
Run, AWS App Runner / ECS Fargate, and Kubernetes" because it only depends on
a small, platform-neutral contract. This script asserts each item of that
contract actually holds in the repo, so the claim is *checked* rather than
asserted. It inspects files only — no app import, no running services — so it
is fast and has no dependencies.

Run via:

    make check-portability
    # or:
    python backend/scripts/check_portability.py

Exit codes:
    0 — every contract item holds
    1 — at least one item is missing (printed as MISS)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str | None:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.exists() else None


_results: list[tuple[bool, str, str]] = []


def check(ok: object, name: str, detail: str = "") -> None:
    _results.append((bool(ok), name, detail))


def has_nonroot_user(dockerfile: str | None) -> bool:
    if not dockerfile:
        return False
    # A `USER <name>` line where the name is not root.
    return bool(re.search(r"^\s*USER\s+(?!root\b)\w+", dockerfile, re.MULTILINE))


def main() -> int:
    backend_df = read("backend/Dockerfile")
    frontend_df = read("frontend/Dockerfile")
    config = read("backend/app/config.py")
    gitignore = read(".gitignore")

    # 1. Standard Docker containers — both services build as images.
    check(backend_df, "backend builds as a Docker image", "backend/Dockerfile")
    check(frontend_df, "frontend builds as a Docker image", "frontend/Dockerfile")

    # 2. Binds to $PORT at runtime (so the platform can inject the port).
    check(
        backend_df and re.search(r"\$\{?PORT", backend_df),
        "backend honours $PORT at runtime",
        "expected ${PORT...} in backend/Dockerfile CMD/HEALTHCHECK",
    )
    check(
        frontend_df and "PORT" in frontend_df,
        "frontend honours $PORT at runtime",
        "expected PORT referenced in frontend/Dockerfile",
    )

    # 3. Non-root container runtime.
    check(has_nonroot_user(backend_df), "backend runs as a non-root USER")
    check(has_nonroot_user(frontend_df), "frontend runs as a non-root USER")

    # 4. HTTP healthchecks declared, hitting the documented endpoints.
    check(
        backend_df and "HEALTHCHECK" in backend_df and "/api/health" in backend_df,
        "backend declares a HEALTHCHECK on /api/health",
    )
    check(
        frontend_df and "HEALTHCHECK" in frontend_df and "/healthz" in frontend_df,
        "frontend declares a HEALTHCHECK on /healthz",
    )

    # 5. Environment-variable configuration (no hardcoded config).
    check(
        config and "BaseSettings" in config,
        "backend config is env-driven (pydantic BaseSettings)",
        "backend/app/config.py",
    )
    check(
        config and "database_url" in config,
        "Postgres is the only required external service (DATABASE_URL)",
    )

    # 6. One-off migration command runs on deploy.
    check(
        backend_df and re.search(r"alembic\s+upgrade\s+head", backend_df),
        "backend applies migrations on start (alembic upgrade head)",
    )

    # 7. Secrets are not committed — .env is ignored.
    check(
        gitignore and re.search(r"^\s*\.env", gitignore, re.MULTILINE),
        ".env is gitignored (secrets stay out of the image/repo)",
    )

    misses = [r for r in _results if not r[0]]
    for ok, name, detail in _results:
        tag = "OK  " if ok else "MISS"
        line = f"{tag}  {name}"
        if not ok and detail:
            line += f"\n        {detail}"
        print(line)

    print()
    print(f"Portability contract: {len(_results) - len(misses)}/{len(_results)} items hold.")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
