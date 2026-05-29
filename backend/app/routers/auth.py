import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.user import User, RefreshToken, ApiKey
from app.schemas.auth import (
    RegisterRequest, LoginRequest,
    UserResponse, ApiKeyCreateRequest, ApiKeyResponse,
)
from app.auth.password import hash_password, verify_password
from app.auth.jwt import create_access_token
from app.auth.api_keys import generate_api_key
from app.auth.dependencies import get_current_user
from app.auth.rate_limiter import check_rate_limit
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


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(request, limit=settings.rate_limit_task_hour)
    result = await db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    )
    user = result.scalar_one_or_none()
    # Check existence and active status first (before expensive bcrypt)
    if not user or not user.password_hash:
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
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Invalid email or password"},
        )

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

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Invalid or expired refresh token"},
        )

    # Rotate: revoke old token, issue new pair
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
    new_key = ApiKey(user_id=current_user.id, key_hash=key_hash, label=payload.label)
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
