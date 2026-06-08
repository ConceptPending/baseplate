"""Admin role-assignment endpoint: PUT /api/admin/users/{id}/roles.

Covers the happy path, unknown-role rejection, and the last-role-holder guard
(the per-role analogue of the admin-users "don't remove the last admin" rule).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.users import UserService
from tests.conftest import _TEST_HASH, TEST_ADMIN_EMAIL


async def _login(client, email: str = TEST_ADMIN_EMAIL) -> str:
    resp = await client.post(
        "/api/auth/login", json={"email": email, "password": "testpass"}
    )
    assert resp.status_code == 200
    return resp.cookies["csrf_token"]


async def _make_admin(db_engine, email: str, roles: set[str]):
    sf = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sf() as s:
        return await UserService.create(
            s, email=email, password_hash=_TEST_HASH, is_admin=True, roles=roles
        )


async def _user_id(client, csrf, email: str) -> str:
    resp = await client.get("/api/admin/users")
    assert resp.status_code == 200
    return next(u["id"] for u in resp.json() if u["email"] == email)


@pytest.mark.asyncio
async def test_list_users_includes_roles(client):
    await _login(client)
    resp = await client.get("/api/admin/users")
    assert resp.status_code == 200
    admin = next(u for u in resp.json() if u["email"] == TEST_ADMIN_EMAIL)
    assert sorted(admin["roles"]) == ["approver", "finance", "reviewer"]


@pytest.mark.asyncio
async def test_assign_roles_to_user(client, db_engine):
    csrf = await _login(client)
    await _make_admin(db_engine, "newbie@example.com", set())
    uid = await _user_id(client, csrf, "newbie@example.com")

    resp = await client.put(
        f"/api/admin/users/{uid}/roles",
        json={"roles": ["approver", "finance"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert sorted(resp.json()["roles"]) == ["approver", "finance"]


@pytest.mark.asyncio
async def test_unknown_role_rejected(client, db_engine):
    csrf = await _login(client)
    await _make_admin(db_engine, "u2@example.com", set())
    uid = await _user_id(client, csrf, "u2@example.com")

    resp = await client.put(
        f"/api/admin/users/{uid}/roles",
        json={"roles": ["approver", "wizard"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422
    assert "wizard" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_system_role_cannot_be_granted_to_a_human(client, db_engine):
    """SYSTEM is a synthetic actor for scheduled jobs — never assignable."""
    csrf = await _login(client)
    await _make_admin(db_engine, "u3@example.com", set())
    uid = await _user_id(client, csrf, "u3@example.com")

    resp = await client.put(
        f"/api/admin/users/{uid}/roles",
        json={"roles": ["system"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 422
    assert "system" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_remove_last_holder_of_a_role(client):
    """The bootstrap admin is the sole holder of every role; stripping one is
    refused with 409, and the roles are left unchanged."""
    csrf = await _login(client)
    uid = await _user_id(client, csrf, TEST_ADMIN_EMAIL)

    resp = await client.put(
        f"/api/admin/users/{uid}/roles",
        json={"roles": ["approver", "reviewer"]},  # drops finance
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 409
    assert "finance" in resp.json()["detail"]

    # unchanged
    me = await client.get("/api/auth/me")
    assert sorted(me.json()["roles"]) == ["approver", "finance", "reviewer"]


@pytest.mark.asyncio
async def test_can_remove_role_once_another_admin_holds_it(client, db_engine):
    """With a second finance admin in place, dropping finance from the first is
    allowed — the role still has a holder."""
    csrf = await _login(client)
    await _make_admin(db_engine, "backup-finance@example.com", {"finance"})
    uid = await _user_id(client, csrf, TEST_ADMIN_EMAIL)

    resp = await client.put(
        f"/api/admin/users/{uid}/roles",
        json={"roles": ["approver", "reviewer"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert "finance" not in resp.json()["roles"]


@pytest.mark.asyncio
async def test_roles_endpoint_requires_auth(client):
    # No login → blocked by the admin gate.
    resp = await client.put(
        "/api/admin/users/00000000-0000-0000-0000-000000000000/roles",
        json={"roles": []},
    )
    assert resp.status_code in (401, 403)
