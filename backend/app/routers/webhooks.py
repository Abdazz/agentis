from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet, InvalidToken
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.webhook import UserWebhook
from app.config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _get_fernet() -> Fernet:
    if not settings.fernet_key:
        raise HTTPException(status_code=500, detail="Webhook encryption not configured")
    key = settings.fernet_key
    return Fernet(key.encode() if isinstance(key, str) else key)


class WebhookCreate(BaseModel):
    url: HttpUrl
    secret: str
    events: str = "task_completed"


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    body: WebhookCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    f = _get_fernet()
    encrypted = f.encrypt(body.secret.encode()).decode()
    wh = UserWebhook(
        user_id=current_user.id,
        url=str(body.url),
        secret_encrypted=encrypted,
        events=body.events,
    )
    db.add(wh)
    await db.commit()
    await db.refresh(wh)
    return {"id": str(wh.id), "url": wh.url, "events": wh.events, "is_active": wh.is_active}


@router.get("")
async def list_webhooks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserWebhook).where(UserWebhook.user_id == current_user.id))
    whs = result.scalars().all()
    return [{"id": str(w.id), "url": w.url, "events": w.events, "is_active": w.is_active} for w in whs]


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wh = await db.get(UserWebhook, UUID(webhook_id))
    if not wh or wh.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await db.delete(wh)
    await db.commit()
    return Response(status_code=204)
