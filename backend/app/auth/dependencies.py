from fastapi import Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User, ApiKey
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
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.revoked_at.is_(None),
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail={"code": "unauthenticated", "message": "Invalid API key"},
            )
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
