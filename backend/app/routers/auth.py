import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from app.database import get_db
from app.models.oidc import OidcConfig
from app.models.org import OrganizationMembership
from app.models.user import User, RefreshToken, ApiKey
from app.schemas.auth import (
    RegisterRequest, LoginRequest,
    UserResponse, ApiKeyCreateRequest, ApiKeyResponse,
    UserProfileUpdate, UserUsageResponse,
)
from app.auth.password import hash_password, verify_password
from app.auth.jwt import create_access_token
from app.auth.api_keys import generate_api_key
from app.auth.dependencies import get_current_user
from app.config import settings

router = APIRouter()

REFRESH_COOKIE = "refresh_token"
REFRESH_TTL = settings.jwt_refresh_ttl


def _make_refresh_token() -> tuple[str, str]:
    """Returns (raw_token, sha256_hash)."""
    raw = secrets.token_hex(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        httponly=True,
        samesite="strict",
        secure=settings.environment != "development",
        max_age=REFRESH_TTL,
        path="/api/v1/auth",
    )


@router.post("/register", status_code=201)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # Case-insensitive email uniqueness check
    result = await db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={"code": "email_taken", "message": "Email already registered"},
        )

    user = User(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        language=payload.language,
    )
    db.add(user)
    await db.flush()  # get user.id without committing

    access_token = create_access_token(str(user.id), user.role.value)
    raw_refresh, refresh_hash = _make_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TTL),
    ))
    await db.commit()

    _set_refresh_cookie(response, raw_refresh)
    return {
        "user": UserResponse(
            id=str(user.id), email=user.email,
            name=user.name, role=user.role.value, language=user.language,
        ),
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl,
    }


async def _redis_login_rate_check(email: str) -> None:
    """Check and increment per-email login failure counter (5 attempts / 15 min)."""
    rate_key = f"login_fails:{email.lower()}"
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
    try:
        fail_count = await redis_client.get(rate_key)
        if fail_count and int(fail_count) >= 5:
            raise HTTPException(
                status_code=429,
                headers={"Retry-After": "900"},
                detail={"code": "rate_limited", "message": "Too many failed login attempts. Try again in 15 minutes."},
            )
    finally:
        await redis_client.aclose()


async def _redis_login_increment(email: str) -> None:
    """Increment per-email login failure counter with 15-min TTL."""
    rate_key = f"login_fails:{email.lower()}"
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
    try:
        await redis_client.incr(rate_key)
        await redis_client.expire(rate_key, 900)
    finally:
        await redis_client.aclose()


async def _redis_login_clear(email: str) -> None:
    """Clear per-email login failure counter on successful login."""
    rate_key = f"login_fails:{email.lower()}"
    redis_client = aioredis.from_url(settings.redis_cache_url, decode_responses=True)
    try:
        await redis_client.delete(rate_key)
    finally:
        await redis_client.aclose()


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # Rate limit: 5 failed attempts per email per 15 minutes
    await _redis_login_rate_check(payload.email)

    result = await db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )
    user = result.scalar_one_or_none()

    if user is None:
        await _redis_login_increment(payload.email)
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Invalid email or password"},
        )

    # BR-AUTH-31: check OIDC org membership BEFORE password_hash guard so that
    # OIDC-provisioned users (password_hash=None) receive 403 not 401.
    oidc_org_result = await db.execute(
        select(OidcConfig)
        .join(OrganizationMembership, OrganizationMembership.organization_id == OidcConfig.org_id)
        .where(
            OrganizationMembership.user_id == user.id,
            OidcConfig.enabled.is_(True),
        )
        .limit(1)
    )
    if oidc_org_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=403,
            detail={"code": "oidc_required", "message": "Password login not allowed; use SSO"},
        )

    if not user.password_hash:
        await _redis_login_increment(payload.email)
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Invalid email or password"},
        )

    if user.deleted_at:
        raise HTTPException(
            status_code=401,
            detail={"code": "account_disabled", "message": "Account disabled"},
        )
    if not verify_password(payload.password, user.password_hash):
        await _redis_login_increment(payload.email)
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Invalid email or password"},
        )

    # Successful login — clear failure counter
    await _redis_login_clear(payload.email)

    access_token = create_access_token(str(user.id), user.role.value)
    raw_refresh, refresh_hash = _make_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TTL),
    ))
    await db.commit()

    _set_refresh_cookie(response, raw_refresh)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl,
    }


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "No refresh token"},
        )

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    # Look up token even if already revoked (to detect replay attacks)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if stored is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Invalid refresh token"},
        )

    if stored.revoked_at is not None:
        # REPLAY ATTACK: token was already revoked — invalidate ALL sessions for this user
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == stored.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await db.commit()
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Refresh token already used — all sessions revoked"},
        )

    if stored.expires_at < now:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Refresh token expired"},
        )

    # Valid — rotate: revoke old, issue new pair
    stored.revoked_at = now
    user = await db.get(User, stored.user_id)
    new_access = create_access_token(str(user.id), user.role.value)
    new_raw, new_hash = _make_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        created_at=now,
        expires_at=now + timedelta(seconds=REFRESH_TTL),
    ))
    await db.commit()

    _set_refresh_cookie(response, new_raw)
    return {
        "access_token": new_access,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl,
    }


@router.post("/logout", status_code=200)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored = result.scalar_one_or_none()
        if stored:
            stored.revoked_at = datetime.now(timezone.utc)
            await db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")
    return {"message": "Logged out"}


@router.post("/api-keys", status_code=201)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # BR-AUTH-32: OIDC-provisioned users cannot create API keys until admin confirms
    if current_user.oidc_pending_confirmation:
        raise HTTPException(
            status_code=403,
            detail={"code": "oidc_pending_confirmation", "message": "Account pending admin confirmation; API key creation is not allowed"},
        )

    count_result = await db.execute(
        select(func.count()).select_from(ApiKey).where(
            ApiKey.user_id == current_user.id,
            ApiKey.revoked_at.is_(None),
        )
    )
    if count_result.scalar() >= 10:
        raise HTTPException(
            status_code=422,
            detail={"code": "too_many_keys", "message": "Maximum 10 active API keys"},
        )

    plaintext, key_hash = generate_api_key()
    new_key = ApiKey(
        user_id=current_user.id,
        key_hash=key_hash,
        label=payload.label,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365),
    )
    db.add(new_key)
    await db.commit()
    await db.refresh(new_key)
    # Plaintext returned ONCE — never stored
    return {"key": plaintext, "label": payload.label, "id": str(new_key.id)}


@router.get("/api-keys")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.user_id == current_user.id,
            ApiKey.revoked_at.is_(None),
        )
    )
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=str(k.id),
            label=k.label,
            created_at=k.created_at.isoformat(),
            expires_at=k.expires_at.isoformat() if k.expires_at else None,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        key_uuid = UUID(key_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_id", "message": "Invalid UUID format"},
        )
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_uuid,
            ApiKey.user_id == current_user.id,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "API key not found"},
        )
    key.revoked_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(
    user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        language=user.language,
        role=user.role.value,
    )


@router.patch("/users/me", response_model=UserResponse)
async def update_current_user_profile(
    body: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    if body.name is not None:
        user.name = body.name
    if body.language is not None:
        user.language = body.language
    await db.flush()
    await db.refresh(user)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        language=user.language,
        role=user.role.value,
    )


@router.get("/users/me/usage", response_model=UserUsageResponse)
async def get_current_user_usage(
    user: User = Depends(get_current_user),
) -> UserUsageResponse:
    return UserUsageResponse(token_used_this_month=user.token_used_this_month or 0)
