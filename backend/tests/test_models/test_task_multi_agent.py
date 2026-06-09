import pytest
import uuid
from datetime import datetime, timezone
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.auth.password import hash_password


@pytest.mark.asyncio
async def test_task_has_parent_task_id(db_session):
    # Create a user first
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"test_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    # Create parent task
    parent = Task(
        id=uuid.uuid4(), user_id=user_id, goal="parent",
        status=TaskStatus.submitted,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(parent)
    await db_session.flush()

    # Create child task with parent_task_id reference
    child = Task(
        id=uuid.uuid4(), user_id=user_id, goal="child",
        status=TaskStatus.submitted, parent_task_id=parent.id,
        agent_role="research",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(child)

    assert child.parent_task_id == parent.id
    assert child.agent_role == "research"
