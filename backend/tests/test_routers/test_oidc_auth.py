"""Tests for OIDC/SSO authentication flow.

Covers:
1. GET /auth/oidc/{slug}  → 302 + PKCE stored in Redis
2. GET /auth/oidc/{slug}  → 404 for unknown org
3. GET /auth/oidc/{slug}  → 404 when OIDC config disabled
4. GET /auth/oidc/callback?error=...  → redirect to /login?error=...
5. GET /auth/oidc/callback with expired/missing state  → 404
6. GET /auth/oidc/callback  → auto-provisions new user + redirects with token
7. GET /auth/oidc/callback  → reuses existing user (no duplicate)
8. POST /auth/login  → 403 oidc_required for user in OIDC org
"""
import base64
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient, Response

TEST_FERNET_KEY = Fernet.generate_key().decode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encrypt_secret(secret: str) -> str:
    return Fernet(TEST_FERNET_KEY.encode()).encrypt(secret.encode()).decode()


def _make_id_token(email: str) -> str:
    """Build a minimal, unsigned JWT that pyjwt can decode with verify_signature=False."""
    import json as _json

    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload_data = {"sub": "abc123", "email": email, "iss": "https://idp.example.com"}
    payload = base64.urlsafe_b64encode(_json.dumps(payload_data).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}."


async def _register_user(client: AsyncClient) -> tuple[str, str]:
    email = f"u_{uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!Secret"},
    )
    assert resp.status_code == 201
    return email, resp.json()["access_token"]


async def _create_org(client: AsyncClient, user_token: str) -> tuple[str, str]:
    slug = f"org-{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Test Org", "slug": slug},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"], resp.json()["slug"]


async def _setup_oidc_config(db_session, org_id: str, enabled: bool = True) -> None:
    """Directly insert an OidcConfig row (bypasses operator-only API)."""
    from app.models.oidc import OidcConfig

    cfg = OidcConfig(
        id=uuid.uuid4(),
        org_id=uuid.UUID(org_id),
        provider="test-idp",
        client_id="test-client-id",
        client_secret=_encrypt_secret("test-secret"),
        discovery_url="https://idp.example.com/.well-known/openid-configuration",
        enabled=enabled,
    )
    db_session.add(cfg)
    await db_session.commit()


# Discovery doc returned by the (mocked) IdP
DISCOVERY_DOC = {
    "authorization_endpoint": "https://idp.example.com/auth",
    "token_endpoint": "https://idp.example.com/token",
    "issuer": "https://idp.example.com",
}


def _make_mock_redis(get_return=None):
    """Build a mock Redis client that behaves like an async context."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=get_return)
    mock.set = AsyncMock()
    mock.delete = AsyncMock()
    mock.aclose = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# Test 1: redirect returns 302 + stores PKCE in Redis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_redirect_returns_302_and_stores_pkce(client: AsyncClient, db_session, monkeypatch):
    """GET /auth/oidc/{slug} returns 302 to IdP and stores PKCE in Redis."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_FERNET_KEY)
    monkeypatch.setattr(app_config.settings, "base_url", "http://localhost:8000")

    _, user_token = await _register_user(client)
    org_id, org_slug = await _create_org(client, user_token)
    await _setup_oidc_config(db_session, org_id, enabled=True)

    mock_redis = _make_mock_redis()

    with patch("app.routers.oidc_auth._fetch_discovery", new=AsyncMock(return_value=DISCOVERY_DOC)), \
         patch("app.routers.oidc_auth.aioredis.from_url", return_value=mock_redis):

        resp = await client.get(
            f"/api/v1/auth/oidc/{org_slug}",
            follow_redirects=False,
        )

    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert "https://idp.example.com/auth" in location
    assert "code_challenge" in location
    assert "state" in location
    assert "client_id=test-client-id" in location
    assert "code_challenge_method=S256" in location

    # Verify Redis.set was called with correct TTL
    mock_redis.set.assert_awaited_once()
    _args, kwargs = mock_redis.set.await_args  # (args, kwargs)
    assert kwargs.get("ex") == 600


# ---------------------------------------------------------------------------
# Test 2: unknown org → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_redirect_unknown_org_returns_404(client: AsyncClient, db_session):
    """GET /auth/oidc/nonexistent-org returns 404."""
    resp = await client.get(
        "/api/v1/auth/oidc/nonexistent-org-slug-xyz",
        follow_redirects=False,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 3: OIDC config disabled → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_redirect_disabled_config_returns_404(client: AsyncClient, db_session):
    """GET /auth/oidc/{slug} returns 404 when OIDC config is disabled."""
    _, user_token = await _register_user(client)
    org_id, org_slug = await _create_org(client, user_token)
    await _setup_oidc_config(db_session, org_id, enabled=False)

    with patch("app.routers.oidc_auth._fetch_discovery", new=AsyncMock(return_value=DISCOVERY_DOC)):
        resp = await client.get(
            f"/api/v1/auth/oidc/{org_slug}",
            follow_redirects=False,
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 4: callback with error param → redirect to /login?error=...
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_callback_with_error_redirects_to_login(client: AsyncClient, db_session, monkeypatch):
    """GET /auth/oidc/callback?error=access_denied redirects to /login?error=access_denied."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "base_url", "http://localhost:8000")

    resp = await client.get(
        "/api/v1/auth/oidc/callback?error=access_denied",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "login?error=access_denied" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Test 5: callback with missing/expired state → 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_callback_expired_state_returns_404(client: AsyncClient, db_session):
    """GET /auth/oidc/callback with expired/missing state returns 404."""
    mock_redis = _make_mock_redis(get_return=None)

    with patch("app.routers.oidc_auth.aioredis.from_url", return_value=mock_redis):
        resp = await client.get(
            "/api/v1/auth/oidc/callback?code=abc&state=deadbeef",
            follow_redirects=False,
        )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "state_expired"


# ---------------------------------------------------------------------------
# Test 6: callback auto-provisions new user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_callback_auto_provisions_new_user(client: AsyncClient, db_session, monkeypatch):
    """Callback auto-provisions a new user and redirects with a JWT token."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_FERNET_KEY)
    monkeypatch.setattr(app_config.settings, "base_url", "http://localhost:8000")

    _, user_token = await _register_user(client)
    org_id, _ = await _create_org(client, user_token)
    await _setup_oidc_config(db_session, org_id, enabled=True)

    new_email = f"sso_{uuid.uuid4().hex[:6]}@corp.example.com"
    id_token = _make_id_token(new_email)
    pkce_payload = json.dumps({"code_verifier": "testverifier", "org_id": org_id})

    mock_redis = _make_mock_redis(get_return=pkce_payload)

    # Build a mock httpx.AsyncClient that returns a valid token response
    mock_http_instance = AsyncMock()
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=False)
    mock_http_instance.post = AsyncMock(
        return_value=Response(200, json={"id_token": id_token, "access_token": "at"})
    )

    with patch("app.routers.oidc_auth._fetch_discovery", new=AsyncMock(return_value=DISCOVERY_DOC)), \
         patch("app.routers.oidc_auth.aioredis.from_url", return_value=mock_redis), \
         patch("app.routers.oidc_auth.httpx.AsyncClient", return_value=mock_http_instance):

        resp = await client.get(
            "/api/v1/auth/oidc/callback?code=authcode&state=somestate",
            follow_redirects=False,
        )

    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert "/tasks?token=" in location

    # Verify user was created in DB
    from sqlalchemy import func, select
    from app.models.user import User
    result = await db_session.execute(
        select(User).where(func.lower(User.email) == new_email.lower())
    )
    created_user = result.scalar_one_or_none()
    assert created_user is not None
    assert created_user.oidc_provider == "test-idp"
    assert created_user.oidc_pending_confirmation is True
    assert created_user.password_hash is None


# ---------------------------------------------------------------------------
# Test 7: callback reuses existing user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_callback_reuses_existing_user(client: AsyncClient, db_session, monkeypatch):
    """Callback does not create a duplicate when user already exists."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_FERNET_KEY)
    monkeypatch.setattr(app_config.settings, "base_url", "http://localhost:8000")

    _, user_token = await _register_user(client)
    org_id, _ = await _create_org(client, user_token)
    await _setup_oidc_config(db_session, org_id, enabled=True)

    # Pre-create the user that SSO will "log in"
    existing_email = f"existing_{uuid.uuid4().hex[:6]}@corp.example.com"
    from app.models.user import User, UserRole
    existing_user = User(
        id=uuid.uuid4(),
        email=existing_email,
        role=UserRole.user,
        oidc_provider="test-idp",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(existing_user)
    await db_session.commit()

    id_token = _make_id_token(existing_email)
    pkce_payload = json.dumps({"code_verifier": "testverifier", "org_id": org_id})
    mock_redis = _make_mock_redis(get_return=pkce_payload)

    mock_http_instance = AsyncMock()
    mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_instance.__aexit__ = AsyncMock(return_value=False)
    mock_http_instance.post = AsyncMock(
        return_value=Response(200, json={"id_token": id_token, "access_token": "at"})
    )

    with patch("app.routers.oidc_auth._fetch_discovery", new=AsyncMock(return_value=DISCOVERY_DOC)), \
         patch("app.routers.oidc_auth.aioredis.from_url", return_value=mock_redis), \
         patch("app.routers.oidc_auth.httpx.AsyncClient", return_value=mock_http_instance):

        resp = await client.get(
            "/api/v1/auth/oidc/callback?code=authcode&state=somestate",
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert "/tasks?token=" in resp.headers["location"]

    # Verify no duplicate users
    from sqlalchemy import func, select
    from app.models.user import User as UserModel
    result = await db_session.execute(
        select(UserModel).where(func.lower(UserModel.email) == existing_email.lower())
    )
    users = result.scalars().all()
    assert len(users) == 1


# ---------------------------------------------------------------------------
# Test 8: password login returns 403 for OIDC org user
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_returns_403_oidc_required_for_oidc_org_user(client: AsyncClient, db_session, monkeypatch):
    """POST /auth/login returns 403 oidc_required for a user in an OIDC-enabled org."""
    import app.config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_FERNET_KEY)

    from app.auth.password import hash_password
    from app.models.oidc import OidcConfig
    from app.models.org import Organization, OrganizationMembership
    from app.models.user import User, UserRole

    # Create user with password
    user_email = f"oidcuser_{uuid.uuid4().hex[:6]}@test.com"
    user = User(
        id=uuid.uuid4(),
        email=user_email,
        password_hash=hash_password("Pass1234!Secret"),
        role=UserRole.user,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)

    # Create org
    org = Organization(
        id=uuid.uuid4(),
        name="SSO Corp",
        slug=f"sso-corp-{uuid.uuid4().hex[:6]}",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(org)
    await db_session.flush()

    # Add user as member
    membership = OrganizationMembership(
        id=uuid.uuid4(),
        organization_id=org.id,
        user_id=user.id,
        role=UserRole.user,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(membership)

    # Add enabled OIDC config for that org
    oidc_cfg = OidcConfig(
        id=uuid.uuid4(),
        org_id=org.id,
        provider="google",
        client_id="gc",
        client_secret=_encrypt_secret("secret"),
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        enabled=True,
    )
    db_session.add(oidc_cfg)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": "Pass1234!Secret"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "oidc_required"
