"""Scheduled (recurring) task CRUD endpoints — Manus-parity "Scheduled Tasks"."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.scheduled_task import ScheduledTask
from app.models.user import User
from app.schemas.scheduled_task import (
    ScheduledTaskCreate, ScheduledTaskUpdate, ScheduledTaskResponse,
)
from app.services.scheduler import compute_next_run

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


@router.get("", response_model=list[ScheduledTaskResponse])
async def list_scheduled_tasks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduledTaskResponse]:
    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == user.id)
        .order_by(ScheduledTask.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", status_code=201, response_model=ScheduledTaskResponse)
async def create_scheduled_task(
    body: ScheduledTaskCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduledTaskResponse:
    sched = ScheduledTask(
        user_id=user.id,
        name=body.name,
        goal_template=body.goal_template,
        cron_expression=body.cron_expression,
        language=body.language,
        allowed_tools=body.allowed_tools,
        max_iterations=body.max_iterations,
        next_run_at=compute_next_run(body.cron_expression),
    )
    db.add(sched)
    await db.commit()
    await db.refresh(sched)
    return sched


@router.get("/{scheduled_task_id}", response_model=ScheduledTaskResponse)
async def get_scheduled_task(
    scheduled_task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduledTaskResponse:
    sched = await db.get(ScheduledTask, scheduled_task_id)
    if sched is None or sched.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scheduled task not found"})
    return sched


@router.patch("/{scheduled_task_id}", response_model=ScheduledTaskResponse)
async def update_scheduled_task(
    scheduled_task_id: UUID,
    body: ScheduledTaskUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScheduledTaskResponse:
    sched = await db.get(ScheduledTask, scheduled_task_id)
    if sched is None or sched.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scheduled task not found"})

    updates = body.model_dump(exclude_unset=True)
    cron_changed = "cron_expression" in updates
    for field, value in updates.items():
        setattr(sched, field, value)
    if cron_changed:
        sched.next_run_at = compute_next_run(sched.cron_expression)

    await db.commit()
    await db.refresh(sched)
    return sched


@router.delete("/{scheduled_task_id}", status_code=204)
async def delete_scheduled_task(
    scheduled_task_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    sched = await db.get(ScheduledTask, scheduled_task_id)
    if sched is None or sched.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Scheduled task not found"})
    await db.delete(sched)
    await db.commit()
