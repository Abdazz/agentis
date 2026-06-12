"""Task template CRUD endpoints (E1)."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.task_template import TaskTemplate
from app.models.user import User, UserRole
from app.schemas.template import TemplateCreate, TemplateResponse

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    category: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateResponse]:
    """List public templates and templates created by the current user."""
    stmt = select(TaskTemplate).where(
        or_(
            TaskTemplate.is_public == True,  # noqa: E712
            TaskTemplate.created_by == user.id,
        )
    )
    if category is not None:
        stmt = stmt.where(TaskTemplate.category == category)
    stmt = stmt.order_by(TaskTemplate.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", status_code=201, response_model=TemplateResponse)
async def create_template(
    body: TemplateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    """Create a new task template."""
    template = TaskTemplate(
        name=body.name,
        description=body.description,
        goal_template=body.goal_template,
        category=body.category,
        created_by=user.id,
        is_public=body.is_public,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a template. Admins can delete any template; users only their own."""
    template = await db.get(TaskTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Template not found"})

    is_admin = user.role in (UserRole.admin, UserRole.operator)
    if not is_admin and template.created_by != user.id:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Cannot delete another user's template"})

    await db.delete(template)
    await db.commit()
