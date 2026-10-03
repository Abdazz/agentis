"""Scheduled (recurring) task engine — the "Scheduled Tasks" feature.

A ScheduledTask holds a goal template + a standard 5-field cron
expression. run_due_scheduled_tasks() (a Celery beat job, see
worker/beat_jobs.py) polls for rows whose next_run_at has passed,
materializes each into a normal Task (through the same repository
function POST /tasks uses), enqueues it exactly like an interactive
submission, and reschedules next_run_at from the cron expression.

Polling on a short interval rather than dynamically registering each
schedule with Celery Beat keeps this simple and consistent with the
existing per-process, no-external-scheduler-service architecture (see
sandbox/manager.py's warm pool for the same "one process reads
DB state and acts" shape).
"""
from datetime import datetime, timezone
from uuid import UUID

import structlog
from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_task import ScheduledTask
from app.models.task import TaskStatus
from app.repositories import task as task_repo

log = structlog.get_logger()


class InvalidCronExpression(ValueError):
    pass


def validate_cron(expression: str) -> None:
    if not croniter.is_valid(expression):
        raise InvalidCronExpression(f"Invalid cron expression: {expression!r}")


def compute_next_run(cron_expression: str, base_time: datetime | None = None) -> datetime:
    base = base_time or datetime.now(timezone.utc)
    return croniter(cron_expression, base).get_next(datetime)


async def run_due_scheduled_tasks(db: AsyncSession, *, now: datetime | None = None) -> dict:
    """Materialize + enqueue every active ScheduledTask that's due. Returns
    {"created": [task ids], "errors": n}. Each schedule is rescheduled even
    if task creation fails for it, so one broken schedule can't wedge the
    whole pool of schedules behind it."""
    from app.worker.tasks import run_agent_task  # local import: avoid a hard Celery
    # dependency for callers (e.g. the router) that only need validate_cron/compute_next_run.

    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.is_active.is_(True),
            ScheduledTask.next_run_at <= now,
        )
    )
    due = result.scalars().all()

    created_task_ids: list[UUID] = []
    error_count = 0
    for sched in due:
        try:
            task = await task_repo.create_task(
                db,
                user_id=sched.user_id,
                goal=sched.goal_template,
                language=sched.language or "en",
                max_iterations=sched.max_iterations or 30,
                allowed_tools=sched.allowed_tools,
            )
            await db.flush()
            run_agent_task.delay(str(task.id))
            sched.last_task_id = task.id
            sched.last_status = TaskStatus.submitted.value
            created_task_ids.append(task.id)
            log.info("scheduled_task_fired", scheduled_task_id=str(sched.id), task_id=str(task.id))
        except Exception as e:
            error_count += 1
            sched.last_status = "schedule_error"
            log.error("scheduled_task_fire_failed", scheduled_task_id=str(sched.id), error=str(e))
        finally:
            sched.last_run_at = now
            sched.next_run_at = compute_next_run(sched.cron_expression, now)

    await db.commit()
    return {"created": created_task_ids, "errors": error_count}
