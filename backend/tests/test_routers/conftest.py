"""Fixtures specific to router tests.

Re-exports the top-level `client` fixture as `async_client` and provides
an `auth_headers` fixture that registers a user and returns Bearer headers.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def async_client(client: AsyncClient) -> AsyncClient:
    """Alias for the shared `client` fixture."""
    return client


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient) -> dict:
    """Register a test user and return Authorization headers."""
    resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "filetest@example.com", "password": "Secure123!Pass"},
    )
    # May already exist (409) — try login instead
    if resp.status_code == 409:
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "filetest@example.com", "password": "Secure123!Pass"},
        )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
