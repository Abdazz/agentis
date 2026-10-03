import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "alice@example.com",
        "password": "Secure123!Pass",
        "name": "Alice",
        "language": "en"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == "alice@example.com"
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Refresh token cookie must be set
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient):
    payload = {"email": "bob@example.com", "password": "Secure123!Pass"}
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


@pytest.mark.asyncio
async def test_register_weak_password_returns_422(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "carol@example.com",
        "password": "weak"
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_case_insensitive_email_dedup(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "Dave@Example.COM",
        "password": "Secure123!Pass"
    })
    response = await client.post("/api/v1/auth/register", json={
        "email": "dave@example.com",
        "password": "Secure123!Pass"
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_without_language_uses_accept_language_header(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "bob-al@example.com", "password": "Secure123!Pass"},
        headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    assert response.status_code == 201
    assert response.json()["user"]["language"] == "en"


@pytest.mark.asyncio
async def test_register_without_language_or_header_uses_operator_default(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "carol-default@example.com", "password": "Secure123!Pass"},
    )
    assert response.status_code == 201
    from app.config import settings
    assert response.json()["user"]["language"] == settings.default_language


@pytest.mark.asyncio
async def test_register_explicit_language_wins_over_header(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "dave-explicit@example.com", "password": "Secure123!Pass", "language": "fr"},
        headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    assert response.status_code == 201
    assert response.json()["user"]["language"] == "fr"
