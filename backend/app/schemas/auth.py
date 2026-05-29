from pydantic import BaseModel, EmailStr, field_validator
from app.auth.password import validate_password_strength


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    language: str = "fr"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        validate_password_strength(v)
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
