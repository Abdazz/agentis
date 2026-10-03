import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import pytest

from app.services.scheduler import (
    validate_cron, compute_next_run, run_due_scheduled_tasks, InvalidCronExpression,
)
from app.models.scheduled_task import ScheduledTask
from app.models.user import User
from app.auth.password import hash_password
from app.database import AsyncSessionLocal


def test_validate_cron_accepts_standard_expression():
    validate_cron("0 9 * * 1")  # every Monday 9am — should not raise


def test_validate_cron_rejects_garbage():
    with pytest.raises(InvalidCronExpression):
        validate_cron("not a cron expression")


def test_compute_next_run_daily_at_9am():
    base = datetime(2026, 6, 10, 10, 0, 0, tzinfo=timezone.utc)  # Wed 10am, past today's 9am
    next_run = compute_next_run("0 9 * * *", base)
    assert next_run.hour == 9
    assert next_run.day == 11  # rolls to tomorrow since today's 9am already passed


def test_compute_next_run_weekly():
    base = datetime(2026, 6, 10, 8, 0, 0, tzinfo=timezone.utc)  # Wednesday
    next_run = compute_next_run("0 9 * * 1", base)  # next Monday
    assert next_run.weekday() == 0  # Monday


@pytest.mark.asyncio
async def test_run_due_scheduled_tasks_fires_due_schedule_and_reschedules(db_session):
    user = User(email=f"sched-{uuid.uuid4().hex[:6]}@t.com", password_hash=hash_password("x"), language="en")
    db_session.add(user)
    await db_session.flush()

    past = datetime.now(timezone.utc).replace(year=2020)
    sched = ScheduledTask(
        user_id=user.id, name="Daily report", goal_template="Summarize yesterday's news",
        cron_expression="0 9 * * *", next_run_at=past,
    )
    db_session.add(sched)
    await db_session.commit()

    with patch("app.worker.tasks.run_agent_task") as mock_task:
        mock_task.delay = MagicMock()
        result = await run_due_scheduled_tasks(db_session)

    assert len(result["created"]) == 1
    assert result["errors"] == 0
    mock_task.delay.assert_called_once()

    await db_session.refresh(sched)
    assert sched.last_task_id is not None
    assert sched.next_run_at > past
    assert sched.last_status == "submitted"


@pytest.mark.asyncio
async def test_run_due_scheduled_tasks_ignores_inactive_and_future_schedules(db_session):
    user = User(email=f"sched2-{uuid.uuid4().hex[:6]}@t.com", password_hash=hash_password("x"), language="en")
    db_session.add(user)
    await db_session.flush()

    future = datetime.now(timezone.utc).replace(year=2099)
    db_session.add(ScheduledTask(
        user_id=user.id, name="Future", goal_template="g", cron_expression="0 9 * * *",
        next_run_at=future,
    ))
    past = datetime.now(timezone.utc).replace(year=2020)
    db_session.add(ScheduledTask(
        user_id=user.id, name="Inactive", goal_template="g", cron_expression="0 9 * * *",
        next_run_at=past, is_active=False,
    ))
    await db_session.commit()

    with patch("app.worker.tasks.run_agent_task") as mock_task:
        mock_task.delay = MagicMock()
        result = await run_due_scheduled_tasks(db_session)

    assert result["created"] == []
    mock_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_run_due_scheduled_tasks_reschedules_even_on_error(db_session):
    user = User(email=f"sched3-{uuid.uuid4().hex[:6]}@t.com", password_hash=hash_password("x"), language="en")
    db_session.add(user)
    await db_session.flush()

    past = datetime.now(timezone.utc).replace(year=2020)
    sched = ScheduledTask(
        user_id=user.id, name="Broken", goal_template="g", cron_expression="0 9 * * *",
        next_run_at=past,
    )
    db_session.add(sched)
    await db_session.commit()

    with patch("app.repositories.task.create_task", side_effect=RuntimeError("db exploded")):
        result = await run_due_scheduled_tasks(db_session)

    assert result["created"] == []
    assert result["errors"] == 1

    await db_session.refresh(sched)
    assert sched.last_status == "schedule_error"
    assert sched.next_run_at > past  # rescheduled despite the failure
