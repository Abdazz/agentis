"""OIDC/SSO authentication flow — PKCE redirect + callback + auto-provision.

Endpoints
---------
GET /auth/oidc/callback            — Exchange code, auto-provision user, issue JWT
GET /auth/oidc/{org_slug}          — Initiate PKCE authorisation redirect

NOTE: callback MUST be declared before {org_slug} in the router so FastAPI
does not treat the literal string "callback" as an org_slug.
"""
import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode
from uuid import UUID as _UUID

import httpx
import jwt as pyjwt
import redis.asyncio as aioredis
import structlog
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import create_access_token
from app.config import settings
from app.database import get_db
from app.models.oidc import OidcConfig
from app.models.org import Organization
from app.models.user import User, UserRole

router = APIRouter(tags=["oidc-auth"])
log = structlog.get_logger()

# Redis key prefix / TTL for PKCE verifiers
_PKCE_PREFIX = "oidc_pkce:"
_PKCE_TTL = 600  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge).

    code_verifier  : 96 random bytes → 128-char URL-safe base64 string
    code_challenge : base64url(SHA-256(code_verifier))
    """
    code_verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(96))
        .rstrip(b"=")
        .decode()
    )
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


def _decrypt_secret(encrypted: str) -> str:
    key = settings.fernet_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "config_error", "message": "Encryption key not configured"},
        )
    return Fernet(key.encode()).decrypt(encrypted.encode()).decode()


async def _fetch_discovery(discovery_url: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.get(discovery_url)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "discovery_failed", "message": "Failed to fetch OIDC discovery document"},
        )
    return resp.json()


async def _get_org_by_slug(slug: str, db: AsyncSession) -> Organization:
    result = await db.execute(
        select(Organization).where(
            Organization.slug == slug,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Organization not found"},
        )
    return org


async def _get_oidc_config(org_id, db: AsyncSession) -> OidcConfig:
    result = await db.execute(
        select(OidcConfig).where(OidcConfig.org_id == org_id)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None or not cfg.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "OIDC not configured or disabled for this organization"},
        )
    return cfg


# ---------------------------------------------------------------------------
# GET /auth/oidc/callback — MUST be declared BEFORE /{org_slug}
# ---------------------------------------------------------------------------

@router.get("/auth/oidc/callback")
async def oidc_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle OIDC callback: exchange code, provision user, redirect with JWT."""
    # IdP returned an error
    if error:
        return RedirectResponse(
            url=f"{settings.base_url}/login?error={error}",
            status_code=302,
        )

    if not state or not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "bad_request", "message": "Missing code or state parameter"},
        )

    # Retrieve PKCE data from Redis
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
    try:
        raw = await redis_client.get(f"{_PKCE_PREFIX}{state}")
        if raw:
            await redis_client.delete(f"{_PKCE_PREFIX}{state}")
    finally:
        await redis_client.aclose()

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "state_expired", "message": "State not found or expired"},
        )

    pkce_data = json.loads(raw)
    code_verifier = pkce_data["code_verifier"]
    org_id = pkce_data["org_id"]

    # Load OIDC config by org_id
    result = await db.execute(
        select(OidcConfig).where(OidcConfig.org_id == _UUID(org_id))
    )
    cfg = result.scalar_one_or_none()
    if cfg is None or not cfg.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "OIDC config not found or disabled"},
        )

    # Fetch discovery document to get token_endpoint
    discovery = await _fetch_discovery(cfg.discovery_url)
    token_endpoint = discovery.get("token_endpoint")
    if not token_endpoint:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "discovery_failed", "message": "Missing token_endpoint in discovery doc"},
        )

    # Decrypt client secret
    client_secret = _decrypt_secret(cfg.client_secret)
    redirect_uri = f"{settings.base_url}/api/v1/auth/oidc/callback"

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=15) as http:
        token_resp = await http.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": cfg.client_id,
                "client_secret": client_secret,
                "code_verifier": code_verifier,
            },
        )

    if token_resp.status_code != 200:
        log.warning("oidc_token_exchange_failed", status=token_resp.status_code, body=token_resp.text)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "token_exchange_failed", "message": "Token exchange with IdP failed"},
        )

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "missing_id_token", "message": "IdP did not return id_token"},
        )

    # Decode JWT payload WITHOUT signature verification (per spec)
    try:
        claims = pyjwt.decode(id_token, options={"verify_signature": False})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "invalid_id_token", "message": f"Cannot decode id_token: {exc}"},
        )

    email = claims.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "missing_email", "message": "id_token does not contain email claim"},
        )

    # Auto-provision: look up or create user  (BR-AUTH-31/32)
    result = await db.execute(
        select(User).where(func.lower(User.email) == email.lower())
    )
    user = result.scalar_one_or_none()
    is_new = user is None

    if is_new:
        user = User(
            email=email,
            role=UserRole.user,
            oidc_provider=cfg.provider,
            oidc_pending_confirmation=True,  # BR-AUTH-32: admin must confirm
            password_hash=None,
        )
        db.add(user)
        await db.flush()
        log.info("oidc_user_provisioned", email=email, org_id=org_id)
    else:
        log.info("oidc_user_login", email=email, org_id=org_id)

    await db.commit()
    await db.refresh(user)

    # Issue JWT
    access_token = create_access_token(str(user.id), user.role.value)

    return RedirectResponse(
        url=f"{settings.base_url}/tasks?token={access_token}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# GET /auth/oidc/{org_slug} — initiate PKCE redirect
# ---------------------------------------------------------------------------

@router.get("/auth/oidc/{org_slug}")
async def oidc_redirect(
    org_slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Redirect the browser to the IdP authorisation endpoint using PKCE."""
    # Resolve org + OIDC config
    org = await _get_org_by_slug(org_slug, db)
    cfg = await _get_oidc_config(org.id, db)

    # Fetch discovery document
    discovery = await _fetch_discovery(cfg.discovery_url)
    authorization_endpoint = discovery.get("authorization_endpoint")
    if not authorization_endpoint:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "discovery_failed", "message": "Missing authorization_endpoint in discovery doc"},
        )

    # Generate PKCE pair and state
    code_verifier, code_challenge = _generate_pkce()
    state = secrets.token_hex(32)

    # Store PKCE data in Redis (TTL 600s)
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
    try:
        await redis_client.set(
            f"{_PKCE_PREFIX}{state}",
            json.dumps({"code_verifier": code_verifier, "org_id": str(org.id)}),
            ex=_PKCE_TTL,
        )
    finally:
        await redis_client.aclose()

    redirect_uri = f"{settings.base_url}/api/v1/auth/oidc/callback"

    params = {
        "client_id": cfg.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    return RedirectResponse(
        url=f"{authorization_endpoint}?{urlencode(params)}",
        status_code=302,
    )
