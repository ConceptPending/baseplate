import pytest


async def _login(client):
    """Helper to log in (cookie is stored on the client automatically)."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "testpass"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_item(client):
    await _login(client)
    response = await client.post(
        "/api/admin/items",
        json={"name": "Test Item", "description": "A test item"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Item"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_list_items(client):
    await _login(client)

    await client.post(
        "/api/admin/items",
        json={"name": "Listed Item"},
    )

    response = await client.get("/api/admin/items")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_update_item(client):
    await _login(client)

    create_resp = await client.post(
        "/api/admin/items",
        json={"name": "Original Name"},
    )
    assert create_resp.status_code == 201
    item_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/admin/items/{item_id}",
        json={"name": "Updated Name", "is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    assert response.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_item(client):
    await _login(client)

    create_resp = await client.post(
        "/api/admin/items",
        json={"name": "To Delete"},
    )
    assert create_resp.status_code == 201
    item_id = create_resp.json()["id"]

    response = await client.delete(f"/api/admin/items/{item_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_public_items(client):
    response = await client.get("/api/public/items")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
