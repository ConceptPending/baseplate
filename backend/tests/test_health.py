import pytest


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Readiness returns 200 when the DB round-trips."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_liveness_endpoint(client):
    """Liveness returns 200 and does not depend on the DB."""
    response = await client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_503_when_db_unreachable(client, monkeypatch):
    """Readiness must report unhealthy (503) when the DB query fails, so an
    orchestrator stops routing traffic to this instance."""
    import app.main as main_module

    class _BrokenSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *args, **kwargs):
            raise RuntimeError("simulated DB outage")

    monkeypatch.setattr(main_module, "async_session", lambda: _BrokenSession())

    response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
