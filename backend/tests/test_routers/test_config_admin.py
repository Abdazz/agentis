import uuid
import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(db_session, role: str) -> "User":
    from app.models.user import User, UserRole
    from app.auth.password import hash_password
    from datetime import datetime, timezone
    user = User(
        id=uuid.uuid4(),
        email=f"{role}_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        role=UserRole(role),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Pass1234!Secret"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# GET /admin/config/llm
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_llm_config_requires_auth(client):
    resp = await client.get("/api/v1/admin/config/llm")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_llm_config_requires_operator_not_admin(client, db_session):
    admin_user = await _make_user(db_session, "admin")
    token = await _login(client, admin_user.email)
    resp = await client.get(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_llm_config_returns_defaults_when_no_db_record(client, db_session):
    op = await _make_user(db_session, "operator")
    token = await _login(client, op.email)
    resp = await client.get(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "model" in data
    assert "api_key_masked" in data
    assert "base_url" in data


@pytest.mark.asyncio
async def test_get_llm_config_reads_db_record(client, db_session):
    import json
    from sqlalchemy import delete
    from app.models.system_config import SystemConfig
    # Clear any existing record from prior tests then seed fresh
    await db_session.execute(delete(SystemConfig).where(SystemConfig.key == "llm_config"))
    await db_session.commit()
    db_session.add(SystemConfig(
        key="llm_config",
        value=json.dumps({
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-testkey123",
            "base_url": "",
        }),
    ))
    await db_session.commit()

    op = await _make_user(db_session, "operator")
    token = await _login(client, op.email)
    resp = await client.get(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o"
    # API key must be masked
    assert data["api_key_masked"] == "sk-t***"
    assert data["base_url"] == ""


# ---------------------------------------------------------------------------
# PATCH /admin/config/llm
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_llm_config_requires_auth(client):
    resp = await client.patch("/api/v1/admin/config/llm", json={"provider": "openai"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_llm_config_requires_operator_not_admin(client, db_session):
    admin_user = await _make_user(db_session, "admin")
    token = await _login(client, admin_user.email)
    resp = await client.patch(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "openai"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_llm_config_creates_record(client, db_session):
    op = await _make_user(db_session, "operator")
    token = await _login(client, op.email)
    resp = await client.patch(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "groq", "model": "llama3-70b", "api_key": "gsk-abc1234", "base_url": ""},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "groq"
    assert data["model"] == "llama3-70b"
    assert data["api_key_masked"] == "gsk-***"
    assert data["base_url"] == ""


@pytest.mark.asyncio
async def test_patch_llm_config_partial_update(client, db_session):
    import json
    from sqlalchemy import delete
    from app.models.system_config import SystemConfig
    # Clear any existing record from prior tests then seed fresh
    await db_session.execute(delete(SystemConfig).where(SystemConfig.key == "llm_config"))
    await db_session.commit()
    db_session.add(SystemConfig(
        key="llm_config",
        value=json.dumps({
            "provider": "anthropic",
            "model": "claude-sonnet-4-5-20251022",
            "api_key": "sk-ant-original",
            "base_url": "",
        }),
    ))
    await db_session.commit()

    op = await _make_user(db_session, "operator")
    token = await _login(client, op.email)
    # Only update the model
    resp = await client.patch(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "claude-opus-4-5"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-opus-4-5"
    # Original key preserved
    assert data["api_key_masked"] == "sk-a***"


@pytest.mark.asyncio
async def test_patch_llm_config_masks_api_key(client, db_session):
    op = await _make_user(db_session, "operator")
    token = await _login(client, op.email)
    resp = await client.patch(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
        json={"api_key": "secretkeyvalue"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "***" in data["api_key_masked"]
    assert "secretkeyvalue" not in data["api_key_masked"]


@pytest.mark.asyncio
async def test_patch_llm_config_empty_api_key_not_stored(client, db_session):
    """Omitting api_key in PATCH body should not overwrite an existing key."""
    import json
    from sqlalchemy import delete
    from app.models.system_config import SystemConfig
    # Clear any existing record from prior tests then seed fresh
    await db_session.execute(delete(SystemConfig).where(SystemConfig.key == "llm_config"))
    await db_session.commit()
    db_session.add(SystemConfig(
        key="llm_config",
        value=json.dumps({
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-existingkey",
            "base_url": "",
        }),
    ))
    await db_session.commit()

    op = await _make_user(db_session, "operator")
    token = await _login(client, op.email)
    # PATCH without api_key field
    resp = await client.patch(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": "gpt-4-turbo"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Existing key should still be preserved
    assert data["api_key_masked"] == "sk-e***"


@pytest.mark.asyncio
async def test_get_after_patch_reflects_new_values(client, db_session):
    op = await _make_user(db_session, "operator")
    token = await _login(client, op.email)

    await client.patch(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
        json={"provider": "ollama", "model": "llama3", "base_url": "http://ollama:11434"},
    )

    resp = await client.get(
        "/api/v1/admin/config/llm",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "ollama"
    assert data["model"] == "llama3"
    assert data["base_url"] == "http://ollama:11434"
