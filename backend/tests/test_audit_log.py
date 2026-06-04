import pytest

from tests.conftest import TEST_ADMIN_EMAIL


async def _login(client) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"email": TEST_ADMIN_EMAIL, "password": "testpass"},
    )
    assert resp.status_code == 200
    return resp.cookies["csrf_token"]


@pytest.mark.asyncio
async def test_create_item_writes_audit_entry(client):
    csrf = await _login(client)
    create = await client.post(
        "/api/admin/items",
        json={"name": "Audited"},
        headers={"X-CSRF-Token": csrf},
    )
    assert create.status_code == 201

    response = await client.get("/api/admin/audit-log")
    assert response.status_code == 200
    entries = response.json()
    assert any(
        e["action"] == "create"
        and e["resource_type"] == "item"
        and e["extra"].get("name") == "Audited"
        for e in entries
    )


@pytest.mark.asyncio
async def test_audit_log_requires_admin(client):
    response = await client.get("/api/admin/audit-log")
    assert response.status_code == 401
