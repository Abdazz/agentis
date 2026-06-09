import json
import uuid as uuid_lib
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from cryptography.fernet import Fernet
from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.user_integration import UserIntegration

router = APIRouter(prefix="/integrations", tags=["integrations"])


class CreateIntegrationRequest(BaseModel):
    provider: str
    credentials: dict[str, Any]


class IntegrationResponse(BaseModel):
    id: str
    provider: str
    is_active: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: UserIntegration) -> "IntegrationResponse":
        return cls(id=str(obj.id), provider=obj.provider, is_active=obj.is_active)


def _encrypt(credentials: dict) -> str:
    if not settings.fernet_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration credentials storage is not configured (AGENTIS_FERNET_KEY missing)"
        )
    f = Fernet(settings.fernet_key.encode())
    return f.encrypt(json.dumps(credentials).encode()).decode()


def _decrypt(encrypted: str) -> dict:
    if not settings.fernet_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Integration credentials storage is not configured (AGENTIS_FERNET_KEY missing)"
        )
    f = Fernet(settings.fernet_key.encode())
    return json.loads(f.decrypt(encrypted.encode()).decode())


@router.post("", response_model=IntegrationResponse, status_code=201)
async def create_integration(
    body: CreateIntegrationRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    encrypted = _encrypt(body.credentials)
    integ = UserIntegration(
        user_id=current_user.id,
        provider=body.provider,
        credentials_encrypted=encrypted,
    )
    db.add(integ)
    await db.commit()
    await db.refresh(integ)
    return IntegrationResponse.from_orm_obj(integ)


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        select(UserIntegration)
        .where(UserIntegration.user_id == current_user.id)
        .where(UserIntegration.is_active == True)  # noqa: E712
        .order_by(UserIntegration.created_at)
    )
    return [IntegrationResponse.from_orm_obj(r) for r in result.scalars().all()]


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.id == uuid_lib.UUID(integration_id),
            UserIntegration.user_id == current_user.id,
        )
    )
    integ = result.scalar_one_or_none()
    if integ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    await db.delete(integ)
    await db.commit()
