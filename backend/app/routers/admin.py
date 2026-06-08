from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import require_admin
from app.models.user import User, UserRole
from app.models.task import Task
from app.models.audit import AuditLog
from app.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def get_stats(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tasks_today = await db.scalar(
        select(func.count(Task.id)).where(Task.created_at >= today_start)
    ) or 0
    active_users = await db.scalar(
        select(func.count(func.distinct(Task.user_id))).where(Task.created_at >= today_start)
    ) or 0
    tokens_this_month = await db.scalar(
        select(func.coalesce(func.sum(User.token_used_this_month), 0))
    ) or 0
    return {
        "tasks_today": tasks_today,
        "active_users": active_users,
        "tokens_this_month": tokens_this_month,
    }


@router.get("/users")
async def list_users(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count(User.id))) or 0
    result = await db.execute(
        select(User).offset(offset).limit(limit).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return {
        "items": [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": u.role.value if hasattr(u.role, "value") else u.role,
                "token_used_this_month": u.token_used_this_month,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.audit import write_audit_event

    user = await db.get(User, UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    allowed_fields = {"role"}
    for field in allowed_fields:
        if field in body:
            setattr(user, field, body[field])
    await db.commit()
    await write_audit_event(
        actor_id=str(admin.id),
        actor_email=admin.email,
        action="user.update",
        resource_type="user",
        resource_id=user_id,
        metadata={k: v for k, v in body.items() if k in allowed_fields},
    )
    return {"id": user_id, "updated": True}


@router.get("/audit")
async def list_audit_events(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    action: str | None = Query(None),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        q = q.where(AuditLog.event_type == action)
    total = await db.scalar(select(func.count(AuditLog.id))) or 0
    result = await db.execute(q.offset(offset).limit(limit))
    events = result.scalars().all()
    return {
        "items": [
            {
                "id": str(e.id),
                "actor_email": e.event_data.get("actor_email", ""),
                "action": e.event_type,
                "resource_type": e.event_data.get("resource_type", ""),
                "resource_id": e.event_data.get("resource_id"),
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "total": total,
    }
