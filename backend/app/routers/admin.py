from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import require_admin
from app.models.user import User, UserRole
from app.models.task import Task
from app.models.audit import AuditLog
from app.models.org import Organization
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


class PatchOrgRequest(BaseModel):
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    allowed_tools: Optional[list[str]] = None
    token_budget_monthly: Optional[int] = None
    max_concurrent_tasks: Optional[int] = None


class OrgConfigResponse(BaseModel):
    id: str
    name: str
    slug: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    allowed_tools: Optional[list[str]] = None
    token_budget_monthly: Optional[int] = None
    max_concurrent_tasks: int


@router.patch("/organizations/{org_id}", response_model=OrgConfigResponse)
async def patch_organization_config(
    org_id: str,
    body: PatchOrgRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Operator endpoint: configure per-org LLM override, tool restrictions, token budget."""
    import uuid as uuid_lib
    result = await db.execute(
        select(Organization).where(
            Organization.id == uuid_lib.UUID(org_id),
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    if body.llm_provider is not None:
        org.llm_provider = body.llm_provider or None
    if body.llm_model is not None:
        org.llm_model = body.llm_model or None
    if body.allowed_tools is not None:
        org.allowed_tools = body.allowed_tools if body.allowed_tools else None
    if body.token_budget_monthly is not None:
        org.token_budget_monthly = body.token_budget_monthly if body.token_budget_monthly > 0 else None
    if body.max_concurrent_tasks is not None:
        org.max_concurrent_tasks = body.max_concurrent_tasks

    await db.commit()
    await db.refresh(org)
    return OrgConfigResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        llm_provider=org.llm_provider,
        llm_model=org.llm_model,
        allowed_tools=org.allowed_tools,
        token_budget_monthly=org.token_budget_monthly,
        max_concurrent_tasks=org.max_concurrent_tasks,
    )


@router.get("/organizations")
async def list_organizations(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.org import OrganizationMembership

    total = await db.scalar(
        select(func.count(Organization.id)).where(Organization.deleted_at.is_(None))
    ) or 0

    result = await db.execute(
        select(
            Organization,
            func.count(OrganizationMembership.id).label("member_count")
        )
        .outerjoin(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(Organization.deleted_at.is_(None))
        .group_by(Organization.id)
        .order_by(Organization.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()
    return {
        "items": [
            {
                "id": str(r.Organization.id),
                "name": r.Organization.name,
                "slug": r.Organization.slug,
                "member_count": r.member_count,
                "token_budget_monthly": r.Organization.token_budget_monthly,
                "created_at": r.Organization.created_at.isoformat(),
            }
            for r in rows
        ],
        "total": total,
    }


@router.delete("/organizations/{org_id}", status_code=204)
async def delete_organization(
    org_id: str,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    from uuid import UUID

    org = await db.get(Organization, UUID(org_id))
    if not org or org.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.deleted_at = datetime.now(timezone.utc)
    await db.commit()
