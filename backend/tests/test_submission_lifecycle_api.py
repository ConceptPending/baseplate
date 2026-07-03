"""Submission lifecycle through the persistence + HTTP layers, with focus on
the system-fired transition the invoice slice didn't have."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.submission import SubmissionCreate
from app.services.submissions import SubmissionService
from app.statespec import GuardRejected, IllegalTransition, PermissionDenied
from app.statespec.submission_spec import STALE_AFTER_DAYS
from tests.conftest import TEST_ADMIN_EMAIL


async def _login(client) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": TEST_ADMIN_EMAIL, "password": "testpass"}
    )
    assert resp.status_code == 200
    return resp.cookies["csrf_token"]


def _payload(**over) -> dict:
    p = {"name": "Jo", "email": "jo@example.com", "message": "Please consider this."}
    p.update(over)
    return p


async def _create(client, csrf, **over):
    resp = await client.post(
        "/api/admin/submissions", json=_payload(**over), headers={"X-CSRF-Token": csrf}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _fire(client, csrf, sid, action):
    return await client.post(
        f"/api/admin/submissions/{sid}/transition",
        json={"action": action},
        headers={"X-CSRF-Token": csrf},
    )


@pytest.mark.asyncio
async def test_create_and_approve(client):
    csrf = await _login(client)
    sub = await _create(client, csrf)
    assert sub["status"] == "pending"
    r = await _fire(client, csrf, sub["id"], "approve")
    assert r.status_code == 200 and r.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_human_cannot_fire_system_transition(client):
    """A reviewer-admin cannot `expire` — that edge is SYSTEM-only — even though
    they hold every human role and the submission is in a valid source state."""
    csrf = await _login(client)
    sub = await _create(client, csrf)
    r = await _fire(client, csrf, sub["id"], "expire")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_request_info_roundtrip(client):
    csrf = await _login(client)
    sub = await _create(client, csrf)
    r = await _fire(client, csrf, sub["id"], "request_info")
    assert r.json()["status"] == "needs_info"
    r = await _fire(client, csrf, sub["id"], "provide_info")
    assert r.json()["status"] == "pending"


async def _backdate(db_engine, submission_id, days):
    """Push a submission's created_at into the past so it reads as stale."""
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        sub = await SubmissionService.get_by_id(s, submission_id)
        sub.created_at = datetime.now(timezone.utc) - timedelta(days=days)
        await s.commit()


@pytest.mark.asyncio
async def test_scheduled_expire_only_touches_stale(client, db_engine):
    """The system job expires stale open submissions and leaves fresh ones —
    the staleness rule living entirely in the spec's guard."""
    csrf = await _login(client)
    stale = await _create(client, csrf, name="Old", email="old@example.com")
    fresh = await _create(client, csrf, name="New", email="new@example.com")
    await _backdate(db_engine, stale["id"], STALE_AFTER_DAYS + 5)

    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        expired = await SubmissionService.expire_stale(s)
    assert expired == 1

    async with sf() as s:
        assert (await SubmissionService.get_by_id(s, stale["id"])).status == "expired"
        assert (await SubmissionService.get_by_id(s, fresh["id"])).status == "pending"


@pytest.mark.asyncio
async def test_guard_blocks_expiring_a_fresh_submission(db_session):
    """Even via the system path, the guard refuses a non-stale submission."""
    sub = await SubmissionService.create(
        db_session, SubmissionCreate(name="x", email="x@example.com", message="hi")
    )
    with pytest.raises(GuardRejected):
        await SubmissionService.transition(
            db_session, sub, "expire", frozenset({"system"})
        )


@pytest.mark.asyncio
async def test_stale_snapshot_cannot_overwrite_a_concurrent_transition(
    db_engine, db_session
):
    """A decision made against a stale in-memory snapshot must refuse rather
    than clobber a transition that landed concurrently (the expiry-job race:
    job loads `pending`, a reviewer approves, job must not flip it to expired)."""
    sub = await SubmissionService.create(
        db_session, SubmissionCreate(name="x", email="x@example.com", message="hi")
    )
    # The refused transition rolls back db_session, expiring its objects —
    # grab the id while it's still loadable without IO.
    sid = sub.id
    # Another actor approves through a different session, behind our back.
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as other:
        concurrent = await SubmissionService.get_by_id(other, sid)
        await SubmissionService.transition(
            other, concurrent, "approve", frozenset({"reviewer"})
        )
    # Our snapshot still reads `pending`, so the engine would allow `reject` —
    # the optimistic write is what must catch the conflict.
    assert sub.status == "pending"
    with pytest.raises(IllegalTransition):
        await SubmissionService.transition(
            db_session, sub, "reject", frozenset({"reviewer"})
        )
    async with sf() as s:
        assert (await SubmissionService.get_by_id(s, sid)).status == "approved"


@pytest.mark.asyncio
async def test_reviewer_role_required_for_human_actions(db_session):
    """A roleless actor can't moderate, mirroring invoice permission gating."""
    sub = await SubmissionService.create(
        db_session, SubmissionCreate(name="x", email="x@example.com", message="hi")
    )
    with pytest.raises(PermissionDenied):
        await SubmissionService.transition(db_session, sub, "approve", frozenset())


@pytest.mark.asyncio
async def test_lifecycle_endpoint(client):
    await _login(client)
    r = await client.get("/api/admin/submissions/lifecycle")
    assert r.status_code == 200
    expire = next(t for t in r.json()["transitions"] if t["name"] == "expire")
    assert expire["roles"] == ["system"]
