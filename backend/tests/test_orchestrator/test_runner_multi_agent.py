"""Tests that runner.py publishes child task results to parent pub/sub channel (Phase 4A)."""
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_runner_publishes_child_task_completion_to_parent_bus(db_session):
    """When child task completes, runner publishes result to parent's pub/sub channel."""
    from app.models.user import User
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    user = User(
        id=uuid.uuid4(),
        email=f"child_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    # Create parent task first (required by foreign key)
    parent_task = Task(
        id=uuid.uuid4(),
        user_id=user.id,
        goal="parent task goal",
        status=TaskStatus.submitted,
        language="en",
        parent_task_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(parent_task)
    await db_session.flush()

    child_task = Task(
        id=uuid.uuid4(),
        user_id=user.id,
        goal="child task goal",
        status=TaskStatus.submitted,
        language="en",
        parent_task_id=parent_task.id,  # This is a child task
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(child_task)
    await db_session.commit()

    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with patch("app.orchestrator.runner.build_llm") as mock_llm, \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]), \
         patch("app.services.agent_team_bus.get_agent_team_bus", return_value=fake_bus):
        mock_llm.return_value = MagicMock()
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(return_value={
            "result_summary": "Task completed successfully",
            "partial": False,
            "artifacts": [],
        })
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(child_task.id), skip_sandbox=True)

    # Verify bus.publish was called exactly once
    assert fake_bus.publish.call_count == 1

    # Verify the call arguments
    call_args = fake_bus.publish.call_args
    assert call_args[0][0] == str(parent_task.id)  # parent_task_id as string
    message = call_args[0][1]
    assert message["subtask_id"] == str(child_task.id)
    assert message["status"] == "completed"
    assert message["result"] == "Task completed successfully"


@pytest.mark.asyncio
async def test_runner_does_not_publish_for_top_level_task(db_session):
    """Top-level tasks (parent_task_id=None) do NOT call bus.publish."""
    from app.models.user import User
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    user = User(
        id=uuid.uuid4(),
        email=f"toplevel_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    top_level_task = Task(
        id=uuid.uuid4(),
        user_id=user.id,
        goal="top level task",
        status=TaskStatus.submitted,
        language="en",
        parent_task_id=None,  # This is a top-level task
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(top_level_task)
    await db_session.commit()

    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()

    with patch("app.orchestrator.runner.build_llm") as mock_llm, \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]), \
         patch("app.services.agent_team_bus.get_agent_team_bus", return_value=fake_bus):
        mock_llm.return_value = MagicMock()
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(return_value={
            "result_summary": "Done",
            "partial": False,
            "artifacts": [],
        })
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(top_level_task.id), skip_sandbox=True)

    # Verify bus.publish was NOT called
    assert fake_bus.publish.call_count == 0
