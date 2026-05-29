import pytest
from httpx import AsyncClient

USER = {"email": "logintest@example.com", "password": "Secure123!Pass"}


@pytest.fixture(autouse=True)
async def create_user(client: AsyncClient):
    await client.post("/api/v1/auth/register", json=USER)


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json=USER)
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": USER["email"], "password": "WrongPass123!"
    })
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": "noone@example.com", "password": "Secure123!Pass"
    })
    assert response.status_code == 401
