import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_users_me_returns_profile(auth_client: AsyncClient):
    resp = await auth_client.get("/api/v1/auth/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "email" in data
    assert "name" in data
    assert "language" in data
    assert "role" in data
    assert "token_used_this_month" not in data


@pytest.mark.asyncio
async def test_get_users_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/auth/users/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_users_me_updates_name(auth_client: AsyncClient):
    resp = await auth_client.patch("/api/v1/auth/users/me", json={"name": "Alice Updated"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Alice Updated"


@pytest.mark.asyncio
async def test_patch_users_me_updates_language(auth_client: AsyncClient):
    resp = await auth_client.patch("/api/v1/auth/users/me", json={"language": "en"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["language"] == "en"


@pytest.mark.asyncio
async def test_patch_users_me_rejects_invalid_language(auth_client: AsyncClient):
    resp = await auth_client.patch("/api/v1/auth/users/me", json={"language": "de"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_users_me_usage(auth_client: AsyncClient):
    resp = await auth_client.get("/api/v1/auth/users/me/usage")
    assert resp.status_code == 200
    data = resp.json()
    assert "token_used_this_month" in data
    assert isinstance(data["token_used_this_month"], int)
