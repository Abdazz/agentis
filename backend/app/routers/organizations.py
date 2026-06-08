from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.org import Organization, OrganizationMembership

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrgCreate(BaseModel):
    name: str
    slug: str


class SetActiveOrg(BaseModel):
    organization_id: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrgCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(select(Organization).where(Organization.slug == body.slug))
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken")
    org = Organization(name=body.name, slug=body.slug, created_at=datetime.now(timezone.utc))
    db.add(org)
    await db.flush()
    member = OrganizationMembership(
        organization_id=org.id,
        user_id=current_user.id,
        role=current_user.role,
        created_at=datetime.now(timezone.utc),
    )
    db.add(member)
    await db.commit()
    await db.refresh(org)
    return {"id": str(org.id), "name": org.name, "slug": org.slug}


@router.get("")
async def list_my_organizations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(OrganizationMembership.user_id == current_user.id)
    )
    orgs = result.scalars().all()
    return [{"id": str(o.id), "name": o.name, "slug": o.slug} for o in orgs]


@router.patch("/active")
async def set_active_organization(
    body: SetActiveOrg,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, UUID(body.organization_id))
    if not org or org.deleted_at:
        raise HTTPException(status_code=404, detail="Organization not found")
    # Attach session to current_user before modification
    user = await db.get(User, current_user.id)
    user.active_organization_id = org.id
    await db.commit()
    return {"active_organization_id": str(org.id)}
