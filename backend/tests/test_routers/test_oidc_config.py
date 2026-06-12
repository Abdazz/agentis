"""Tests for POST/GET /api/v1/admin/organizations/{org_id}/oidc"""
import pytest
import uuid
from cryptography.fernet import Fernet
from httpx import AsyncClient

TEST_OIDC_KEY = Fernet.generate_key().decode()

OIDC_BODY = {
    "provider": "google",
    "client_id": "my-client-id",
    "client_secret": "super-secret",
    "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
    "enabled": True,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user_and_token(client: AsyncClient) -> tuple[str, str]:
    email = f"u_{uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!Secret"},
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return email, token


async def _make_admin_token(client: AsyncClient, db_session) -> str:
    from app.models.user import User, UserRole
    from app.auth.password import hash_password
    from datetime import datetime, timezone

    u = User(
        id=uuid.uuid4(),
        email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        role=UserRole.admin,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(u)
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": u.email, "password": "Pass1234!Secret"},
    )
    return login.json()["access_token"]


async def _make_operator_token(client: AsyncClient, db_session) -> str:
    from app.models.user import User, UserRole
    from app.auth.password import hash_password
    from datetime import datetime, timezone

    op = User(
        id=uuid.uuid4(),
        email=f"op_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        role=UserRole.operator,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(op)
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": op.email, "password": "Pass1234!Secret"},
    )
    return login.json()["access_token"]


async def _create_org(client: AsyncClient, user_token: str) -> str:
    slug = f"org-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Test Org", "slug": slug},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_oidc_creates_config_and_redacts_secret(client: AsyncClient, db_session, monkeypatch):
    """POST creates OIDC config and returns client_secret as '***'."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_OIDC_KEY)

    _, user_token = await _make_user_and_token(client)
    op_token = await _make_operator_token(client, db_session)
    org_id = await _create_org(client, user_token)

    resp = await client.post(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        json=OIDC_BODY,
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["provider"] == "google"
    assert data["client_id"] == "my-client-id"
    assert data["client_secret"] == "***"
    assert data["discovery_url"] == OIDC_BODY["discovery_url"]
    assert data["enabled"] is True
    assert data["org_id"] == org_id
    assert "id" in data


@pytest.mark.asyncio
async def test_post_oidc_updates_existing_config(client: AsyncClient, db_session, monkeypatch):
    """POST is an upsert — calling it twice updates the existing row."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_OIDC_KEY)

    _, user_token = await _make_user_and_token(client)
    op_token = await _make_operator_token(client, db_session)
    org_id = await _create_org(client, user_token)

    r1 = await client.post(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        json=OIDC_BODY,
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert r1.status_code == 201

    updated_body = {**OIDC_BODY, "provider": "azure", "enabled": False}
    resp2 = await client.post(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        json=updated_body,
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp2.status_code == 201, resp2.text
    data = resp2.json()
    assert data["provider"] == "azure"
    assert data["enabled"] is False
    assert data["client_secret"] == "***"


@pytest.mark.asyncio
async def test_get_oidc_returns_config_with_redacted_secret(client: AsyncClient, db_session, monkeypatch):
    """GET returns OIDC config with client_secret always '***'."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_OIDC_KEY)

    _, user_token = await _make_user_and_token(client)
    op_token = await _make_operator_token(client, db_session)
    org_id = await _create_org(client, user_token)

    r1 = await client.post(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        json=OIDC_BODY,
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert r1.status_code == 201

    resp = await client.get(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["client_secret"] == "***"
    assert data["provider"] == "google"
    assert data["org_id"] == org_id


@pytest.mark.asyncio
async def test_get_oidc_returns_404_when_no_config(client: AsyncClient, db_session):
    """GET returns 404 when no OIDC config exists for the org."""
    _, user_token = await _make_user_and_token(client)
    op_token = await _make_operator_token(client, db_session)
    org_id = await _create_org(client, user_token)

    resp = await client.get(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_oidc_requires_operator_unauthenticated(client: AsyncClient, db_session):
    """POST /oidc returns 401 for unauthenticated requests."""
    _, user_token = await _make_user_and_token(client)
    org_id = await _create_org(client, user_token)

    resp = await client.post(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        json=OIDC_BODY,
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_oidc_requires_operator_not_admin(client: AsyncClient, db_session, monkeypatch):
    """POST /oidc returns 403 for admin role (not operator)."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_OIDC_KEY)

    _, user_token = await _make_user_and_token(client)
    admin_token = await _make_admin_token(client, db_session)
    org_id = await _create_org(client, user_token)

    resp = await client.post(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        json=OIDC_BODY,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_oidc_requires_operator_not_user(client: AsyncClient, db_session):
    """GET /oidc returns 403 for regular user role."""
    _, user_token = await _make_user_and_token(client)
    org_id = await _create_org(client, user_token)

    resp = await client.get(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_post_oidc_org_not_found(client: AsyncClient, db_session, monkeypatch):
    """POST returns 404 for a non-existent org_id."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_OIDC_KEY)

    op_token = await _make_operator_token(client, db_session)
    fake_org_id = str(uuid.uuid4())

    resp = await client.post(
        f"/api/v1/admin/organizations/{fake_org_id}/oidc",
        json=OIDC_BODY,
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_oidc_no_fernet_key_returns_503(client: AsyncClient, db_session, monkeypatch):
    """POST returns 503 when AGENTIS_FERNET_KEY is not configured."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", "")

    _, user_token = await _make_user_and_token(client)
    op_token = await _make_operator_token(client, db_session)
    org_id = await _create_org(client, user_token)

    resp = await client.post(
        f"/api/v1/admin/organizations/{org_id}/oidc",
        json=OIDC_BODY,
        headers={"Authorization": f"Bearer {op_token}"},
    )
    assert resp.status_code == 503
    assert "AGENTIS_FERNET_KEY" in resp.json()["error"]["message"]
