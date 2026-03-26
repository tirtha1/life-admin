"""
Integration tests for the API service health endpoint.
Requires running Postgres (uses TEST_DATABASE_URL env var).
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client():
    """ASGI test client for the API service."""
    from services.api.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "lifeadmin-api"


@pytest.mark.asyncio
async def test_bills_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/bills")
    assert response.status_code == 403  # No Bearer token


@pytest.mark.asyncio
async def test_dev_token_endpoint(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/token",
        json={"user_id": "00000000-0000-0000-0000-000000000001", "email": "test@example.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
