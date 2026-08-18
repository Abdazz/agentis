from typing import Literal, Optional
from pydantic import BaseModel, EmailStr, field_validator
from app.auth.password import validate_password_strength


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    # None means "not specified" — the register endpoint falls back to the
    # Accept-Language header, then the operator's configured default
    # (BR-LANG-01). Explicit values are still restricted to en/fr.
    language: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        validate_password_strength(v)
        return v

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v is not None and v not in ("en", "fr"):
            raise ValueError("language must be 'en' or 'fr'")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    role: str
    language: str


class ApiKeyCreateRequest(BaseModel):
    label: str | None = None


class ApiKeyResponse(BaseModel):
    id: str
    label: str | None
    created_at: str
    expires_at: str | None
    last_used_at: str | None


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    language: Optional[Literal["fr", "en"]] = None


class UserUsageResponse(BaseModel):
    token_used_this_month: int
