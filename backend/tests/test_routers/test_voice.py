import pytest
import uuid
from unittest.mock import patch
from httpx import AsyncClient


async def _make_user_and_token(client: AsyncClient) -> str:
    email = f"user_{uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post("/api/v1/auth/register",
                             json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    login = await client.post("/api/v1/auth/login",
                              json={"email": email, "password": "Pass1234!Secret"})
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_transcribe_returns_text(client: AsyncClient):
    token = await _make_user_and_token(client)
    with patch("app.routers.voice.transcribe_bytes",
               return_value={"text": "hello world", "language": "en", "duration_seconds": 2.5}):
        resp = await client.post(
            "/api/v1/voice/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", b"\x00" * 100, "audio/wav")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "hello world"
    assert data["language"] == "en"


@pytest.mark.asyncio
async def test_transcribe_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("test.wav", b"\x00" * 100, "audio/wav")},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_synthesize_returns_audio(client: AsyncClient):
    token = await _make_user_and_token(client)
    with patch("app.routers.voice.synthesize_text", return_value=b"fake-mp3-bytes"):
        resp = await client.post(
            "/api/v1/voice/synthesize",
            json={"text": "Bonjour le monde"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == b"fake-mp3-bytes"


@pytest.mark.asyncio
async def test_synthesize_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/voice/synthesize",
        json={"text": "hello"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_transcribe_returns_503_when_unavailable(client: AsyncClient):
    token = await _make_user_and_token(client)
    with patch("app.routers.voice.transcribe_bytes",
               side_effect=RuntimeError("faster-whisper is not installed")):
        resp = await client.post(
            "/api/v1/voice/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"audio": ("test.wav", b"\x00" * 100, "audio/wav")},
        )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_synthesize_returns_503_when_unavailable(client: AsyncClient):
    token = await _make_user_and_token(client)
    with patch("app.routers.voice.synthesize_text",
               side_effect=RuntimeError("edge-tts is not installed")):
        resp = await client.post(
            "/api/v1/voice/synthesize",
            json={"text": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503
