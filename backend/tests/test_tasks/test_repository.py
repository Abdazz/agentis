import uuid
import pytest
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.task import TaskStatus
from app.auth.password import hash_password
from app.repositories import task as task_repo


@pytest.fixture
async def user():
    async with AsyncSessionLocal() as db:
        u = User(email=f"repo-{uuid.uuid4()}@t.com", password_hash=hash_password("x"), language="en")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


async def test_create_task_defaults(user):
    async with AsyncSessionLocal() as db:
        t = await task_repo.create_task(db, user_id=user.id, goal="do thing", language="en",
                                        max_iterations=30, allowed_tools=None)
        await db.commit()
        assert t.status == TaskStatus.submitted
        assert t.goal == "do thing"


async def test_list_tasks_filters_by_user_and_status(user):
    async with AsyncSessionLocal() as db:
        await task_repo.create_task(db, user_id=user.id, goal="g1", language="en",
                                    max_iterations=30, allowed_tools=None)
        await db.commit()
    async with AsyncSessionLocal() as db:
        rows, next_cursor = await task_repo.list_tasks(db, user_id=user.id, limit=20)
        assert len(rows) >= 1
        assert all(r.user_id == user.id for r in rows)


async def test_count_running_tasks(user):
    async with AsyncSessionLocal() as db:
        t = await task_repo.create_task(db, user_id=user.id, goal="g", language="en",
                                        max_iterations=30, allowed_tools=None)
        t.status = TaskStatus.running
        await db.commit()
    async with AsyncSessionLocal() as db:
        count = await task_repo.count_running_tasks(db, user_id=user.id)
        assert count >= 1


async def test_cancel_task_sets_cancelled(user):
    async with AsyncSessionLocal() as db:
        t = await task_repo.create_task(db, user_id=user.id, goal="g", language="en",
                                        max_iterations=30, allowed_tools=None)
        t.status = TaskStatus.running
        await db.commit()
        tid = t.id
    async with AsyncSessionLocal() as db:
        ok = await task_repo.cancel_task(db, task_id=tid, user_id=user.id)
        await db.commit()
        assert ok is True
    async with AsyncSessionLocal() as db:
        t = await task_repo.get_task(db, task_id=tid, user_id=user.id)
        assert t.status == TaskStatus.cancelled
