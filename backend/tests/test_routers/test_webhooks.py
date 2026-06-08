import pytest
import uuid
import os
from httpx import AsyncClient
from app import config as app_config

FERNET_KEY = "ff2prYOmD99Mo3ReVab2jAREOVGfkVgZFKcU2h9mV-M="


def _make_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_webhook(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(app_config.settings, "fernet_key", FERNET_KEY)
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "https://example.com/hook", "secret": "mysecret", "events": "task_completed"},
        headers=_make_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["url"] == "https://example.com/hook"
    assert "secret" not in data
    assert "secret_encrypted" not in data


@pytest.mark.asyncio
async def test_list_webhooks(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(app_config.settings, "fernet_key", FERNET_KEY)
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    await client.post(
        "/api/v1/webhooks",
        json={"url": "https://ex.com/h", "secret": "s", "events": "task_completed"},
        headers=_make_headers(token),
    )
    resp = await client.get("/api/v1/webhooks", headers=_make_headers(token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_delete_webhook(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(app_config.settings, "fernet_key", FERNET_KEY)
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    cr = await client.post(
        "/api/v1/webhooks",
        json={"url": "https://del.com/h", "secret": "s2", "events": "task_completed"},
        headers=_make_headers(token),
    )
    wh_id = cr.json()["id"]
    resp = await client.delete(f"/api/v1/webhooks/{wh_id}", headers=_make_headers(token))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_invalid_url_rejected(client: AsyncClient):
    email = f"u_{uuid.uuid4().hex[:8]}@test.com"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": "Pass1234!Secret"})
    token = r.json()["access_token"]
    resp = await client.post(
        "/api/v1/webhooks",
        json={"url": "not-a-url", "secret": "s", "events": "task_completed"},
        headers=_make_headers(token),
    )
    assert resp.status_code == 422
