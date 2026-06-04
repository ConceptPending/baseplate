from uuid import uuid4

import pytest

from app.services.users import LastAdminError, UserService
from tests.conftest import TEST_ADMIN_EMAIL


async def _login(client) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": "testpass"},
    )
    assert resp.status_code == 200
    return resp.cookies["csrf_token"]


@pytest.mark.asyncio
async def test_admin_can_list_users(client):
    await _login(client)
    response = await client.get("/api/admin/users")
    assert response.status_code == 200
    emails = [u["email"] for u in response.json()]
    assert TEST_ADMIN_EMAIL in emails


@pytest.mark.asyncio
async def test_invite_user(client):
    csrf = await _login(client)
    response = await client.post(
        "/api/admin/users",
        json={"email": "second@example.com", "is_admin": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "second@example.com"
    assert body["is_active"] is True
    # The initial password must never be returned.
    assert "password" not in body and "temporary_password" not in body


@pytest.mark.asyncio
async def test_cannot_deactivate_self(client):
    csrf = await _login(client)
    me = (await client.get("/api/auth/me")).json()
    response = await client.patch(
        f"/api/admin/users/{me['id']}/active",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400
    assert "Cannot deactivate yourself" in response.json()["detail"]


@pytest.mark.asyncio
async def test_set_active_refuses_last_admin(db_session):
    """When only one active admin exists, a *different* actor deactivating them
    hits the last-admin guard. (Via the API the self-check shadows this path,
    so we exercise the service directly — it's the load-bearing safety net.)"""
    admin = await UserService.get_by_email(db_session, TEST_ADMIN_EMAIL)
    with pytest.raises(LastAdminError):
        await UserService.set_active(
            db_session, admin.id, is_active=False, actor_id=uuid4()
        )


@pytest.mark.asyncio
async def test_set_admin_refuses_demoting_last_admin(db_session):
    admin = await UserService.get_by_email(db_session, TEST_ADMIN_EMAIL)
    with pytest.raises(LastAdminError):
        await UserService.set_admin(
            db_session, admin.id, is_admin=False, actor_id=uuid4()
        )
