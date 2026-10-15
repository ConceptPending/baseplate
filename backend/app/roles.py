"""The application's role vocabulary — the single list of who-can-be-what.

Roles are held per-user (`User.roles`) and referenced by lifecycle specs
(see `app/statespec/invoice_spec.py`) to gate transitions. Keeping the names
here means the user model, the specs, and any future admin UI all agree on one
catalogue instead of trading bare strings.

`is_admin` and roles are *orthogonal*: `is_admin` is the gate to the admin area
at all; roles say what an admin is authorised to *do* once inside (an admin can
exist with zero lifecycle roles). New lifecycle? Add its roles here.

Stored on the row as a sorted, comma-separated string so the column is portable
across SQLite (tests) and Postgres (prod) without array/JSON types.
"""

from __future__ import annotations

from collections.abc import Iterable

# Invoice review lifecycle roles. Separation of duties: the role that approves
# an invoice is not the role that pays it.
REVIEWER = "reviewer"
APPROVER = "approver"
FINANCE = "finance"

# A synthetic actor for transitions fired by the system itself — scheduled
# jobs, not people (e.g. auto-expiring a stale submission). It gates engine
# edges like any other role, but it is NEVER assignable to a human: a request
# to grant it via the admin API is rejected. This split (human-grantable vs.
# the full engine vocabulary) was forced by the submission lifecycle's
# system-fired `expire` transition — the invoice lifecycle never needed it.
SYSTEM = "system"

# Roles a human user can be granted (what the admin role-assignment endpoint and
# the bootstrap admin draw from).
HUMAN_ROLES: frozenset[str] = frozenset({REVIEWER, APPROVER, FINANCE})

# Every role the engine recognises, including synthetic actors. Specs validate
# their edges against this; the assignment endpoint validates against the
# narrower HUMAN_ROLES.
ALL_ROLES: frozenset[str] = HUMAN_ROLES | {SYSTEM}


def parse_roles(raw: str | None) -> frozenset[str]:
    """CSV string -> set of roles. Tolerant of whitespace, blanks, and None."""
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def format_roles(roles: Iterable[str]) -> str:
    """Set of roles -> canonical sorted CSV string for storage."""
    return ",".join(sorted(set(roles)))


def unknown_roles(roles: Iterable[str]) -> set[str]:
    """Roles the engine doesn't recognise at all (spec-level validation)."""
    return set(roles) - ALL_ROLES


def nonassignable_roles(roles: Iterable[str]) -> set[str]:
    """Roles that may not be granted to a human — unknown ones plus synthetic
    actors like SYSTEM. Used by the admin role-assignment endpoint."""
    return set(roles) - HUMAN_ROLES
