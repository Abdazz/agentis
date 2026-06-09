import pytest
import uuid
from cryptography.fernet import Fernet
from httpx import AsyncClient


TEST_KEY = Fernet.generate_key().decode()


async def _make_user_and_token(client: AsyncClient) -> str:
    email = f"user_{uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post("/api/v1/auth/register",
                             json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    login = await client.post("/api/v1/auth/login",
                              json={"email": email, "password": "Pass1234!Secret"})
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_create_integration(client, db_session, monkeypatch):
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_KEY)
    token = await _make_user_and_token(client)
    resp = await client.post(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "provider": "smtp",
            "credentials": {"host": "smtp.gmail.com", "port": 587, "username": "user@gmail.com", "password": "secret"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["provider"] == "smtp"
    assert "credentials" not in data  # secret never returned


@pytest.mark.asyncio
async def test_list_integrations(client, db_session, monkeypatch):
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_KEY)
    token = await _make_user_and_token(client)
    await client.post(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "caldav", "credentials": {"url": "https://cal.example.com"}},
    )
    resp = await client.get("/api/v1/integrations",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert any(i["provider"] == "caldav" for i in resp.json())


@pytest.mark.asyncio
async def test_delete_integration(client, db_session, monkeypatch):
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_KEY)
    token = await _make_user_and_token(client)
    create = await client.post(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "smtp", "credentials": {"host": "smtp.example.com"}},
    )
    integ_id = create.json()["id"]
    del_resp = await client.delete(f"/api/v1/integrations/{integ_id}",
                                   headers={"Authorization": f"Bearer {token}"})
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_integration_requires_auth(client):
    resp = await client.get("/api/v1/integrations")
    assert resp.status_code == 401
