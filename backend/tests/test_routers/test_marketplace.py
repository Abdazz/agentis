import pytest
import uuid as _uuid
from httpx import AsyncClient


async def _make_user_and_token(client: AsyncClient) -> str:
    email = f"user_{_uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post("/api/v1/auth/register",
                             json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    login = await client.post("/api/v1/auth/login",
                              json={"email": email, "password": "Pass1234!Secret"})
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_list_plugins_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/marketplace/plugins")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_plugins_returns_results(client: AsyncClient):
    token = await _make_user_and_token(client)
    resp = await client.get(
        "/api/v1/marketplace/plugins",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_plugins_filter_installed(client: AsyncClient):
    token = await _make_user_and_token(client)
    resp = await client.get(
        "/api/v1/marketplace/plugins?installed=false",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(not p["installed"] for p in data)
