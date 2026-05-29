import jwt
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.config import settings


class TokenExpiredError(Exception):
    pass


class TokenInvalidError(Exception):
    pass


def _load_private_key() -> str:
    return Path(settings.jwt_private_key_path).read_text()


def _load_public_key() -> str:
    return Path(settings.jwt_public_key_path).read_text()


def create_access_token(
    user_id: str,
    role: str,
    org_id: str | None = None,
    ttl: timedelta | None = None,
) -> str:
    if ttl is None:
        ttl = timedelta(seconds=settings.jwt_access_ttl)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "org_id": org_id,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _load_private_key(), algorithm="RS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _load_public_key(), algorithms=["RS256"])
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except jwt.PyJWTError as e:
        raise TokenInvalidError(f"Invalid token: {e}")
