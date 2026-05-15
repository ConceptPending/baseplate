import pytest


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    response = await client.post(
        "/api/auth/login",
        json={"username": "wrong", "password": "wrong"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_success(client):
    response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "testpass"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Login successful"
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_logout(client):
    response = await client.post("/api/auth/logout")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_without_auth(client):
    response = await client.get("/api/admin/items")
    assert response.status_code == 401
