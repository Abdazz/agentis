"""Task persistence + queries (Features TASK-1, TASK-3, TASK-4)."""
import base64
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task, TaskStatus

_ACTIVE_RUNNING = (TaskStatus.submitted, TaskStatus.planning, TaskStatus.running,
                   TaskStatus.waiting_for_input)


def _encode_cursor(created_at: datetime, task_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{task_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, tid = raw.split("|")
    return datetime.fromisoformat(ts), UUID(tid)


async def create_task(db: AsyncSession, *, user_id: UUID, goal: str, language: str,
                      max_iterations: int, allowed_tools: list[str] | None,
                      organization_id: UUID | None = None,
                      notify_webhook: str | None = None) -> Task:
    task = Task(
        user_id=user_id, goal=goal, language=language, max_iterations=max_iterations,
        allowed_tools=allowed_tools, organization_id=organization_id,
        notify_webhook=notify_webhook, status=TaskStatus.submitted,
    )
    db.add(task)
    await db.flush()
    return task


async def get_task(db: AsyncSession, *, task_id: UUID, user_id: UUID | None = None,
                   is_admin: bool = False) -> Task | None:
    stmt = select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
    if not is_admin and user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def count_running_tasks(db: AsyncSession, *, user_id: UUID) -> int:
    stmt = select(func.count()).select_from(Task).where(
        Task.user_id == user_id,
        Task.status.in_(_ACTIVE_RUNNING),
        Task.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one()


async def list_tasks(db: AsyncSession, *, user_id: UUID | None, is_admin: bool = False,
                     statuses: list[TaskStatus] | None = None, language: str | None = None,
                     created_after: datetime | None = None, created_before: datetime | None = None,
                     search: str | None = None, after_cursor: str | None = None,
                     limit: int = 20, include_deleted: bool = False) -> tuple[list[Task], str | None]:
    conditions = []
    if not is_admin and user_id is not None:
        conditions.append(Task.user_id == user_id)
    if not include_deleted:
        conditions.append(Task.deleted_at.is_(None))
    if statuses:
        conditions.append(Task.status.in_(statuses))
    if language:
        conditions.append(Task.language == language)
    if created_after:
        conditions.append(Task.created_at >= created_after)
    if created_before:
        conditions.append(Task.created_at <= created_before)
    if search:
        conditions.append(func.to_tsvector("simple", Task.goal).op("@@")(
            func.plainto_tsquery("simple", search)))
    if after_cursor:
        c_ts, c_id = _decode_cursor(after_cursor)
        conditions.append(
            (Task.created_at < c_ts) | and_(Task.created_at == c_ts, Task.id < c_id))

    stmt = (select(Task).where(and_(*conditions))
            .order_by(Task.created_at.desc(), Task.id.desc())
            .limit(limit + 1))
    rows = list((await db.execute(stmt)).scalars().all())

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)
    return rows, next_cursor


async def cancel_task(db: AsyncSession, *, task_id: UUID, user_id: UUID,
                      is_admin: bool = False) -> bool:
    """Cancel a task from any state except completed/failed (BR-TASK-20).
    Idempotent (BR-TASK-23): cancelling an already-cancelled task returns True."""
    task = await get_task(db, task_id=task_id, user_id=user_id, is_admin=is_admin)
    if task is None:
        return False
    if task.status in (TaskStatus.completed, TaskStatus.failed):
        return False
    if task.status == TaskStatus.cancelled:
        return True
    task.status = TaskStatus.cancelled
    task.completed_at = datetime.now(timezone.utc)
    return True
