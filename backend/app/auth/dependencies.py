from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, Request, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User, ApiKey, UserRole
from app.auth.jwt import decode_access_token, TokenExpiredError, TokenInvalidError
from app.auth.api_keys import hash_api_key


async def get_current_user(
    request: Request,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Check API key first (X-API-Key header)
    if x_api_key:
        key_hash = hash_api_key(x_api_key)
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.revoked_at.is_(None),
                (ApiKey.expires_at.is_(None)) | (ApiKey.expires_at > now),
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail={"code": "unauthenticated", "message": "Invalid API key"},
            )
        # Update last_used_at (debounced: only if older than 60 seconds)
        if api_key.last_used_at is None or (now - api_key.last_used_at) > timedelta(seconds=60):
            api_key.last_used_at = now
            await db.flush()
        user = await db.get(User, api_key.user_id)
        if not user or user.deleted_at:
            raise HTTPException(
                status_code=401,
                detail={"code": "unauthenticated", "message": "User not found"},
            )
        return user

    # Fall back to JWT Bearer
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Missing credentials"},
        )
    token = auth_header[7:]
    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=401,
            detail={"code": "token_expired", "message": "Access token expired"},
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Invalid token"},
        )

    user = await db.get(User, payload["sub"])
    if not user or user.deleted_at:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "User not found"},
        )
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Allow only admin and operator roles (spec §3.2 RBAC)."""
    if current_user.role not in (UserRole.admin, UserRole.operator):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def require_operator(current_user: User = Depends(get_current_user)) -> User:
    """Allow only the operator role (highest privilege — spec §3.2 RBAC)."""
    if current_user.role != UserRole.operator:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator access required")
    return current_user


async def verify_token_string(token: str) -> User:
    """Verify a raw JWT string (for WebSocket query param auth)."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        try:
            payload = decode_access_token(token)
        except (TokenExpiredError, TokenInvalidError):
            raise HTTPException(status_code=401, detail="Invalid token")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.get(User, user_id)
        if user is None or user.deleted_at:
            raise HTTPException(status_code=401, detail="User not found")
        return user
