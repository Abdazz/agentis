"""Tests that runner.py injects dispatch_subtask + gather_results for supervisor agents (BR-MULTI-01)."""
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_supervisor_agent_gets_dispatch_and_gather_tools(db_session):
    """Verify that supervisor agents have dispatch_subtask and gather_results injected."""
    from app.models.user import User
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    user = User(
        id=uuid.uuid4(),
        email=f"supervisor_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="coordinate subtasks",
        status=TaskStatus.submitted, language="en",
        agent_role="supervisor",  # Supervisor agent
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.commit()

    captured_run_contexts = []

    def capture_run_context(initial, config):
        """Capture RunContext from config to verify allowed_tools."""
        run_ctx = config.get("configurable", {}).get("run_ctx")
        if run_ctx:
            captured_run_contexts.append(run_ctx)
        return {
            "result_summary": "done", "partial": False, "artifacts": []
        }

    with patch("app.orchestrator.runner.build_llm") as mock_build_llm, \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]):
        mock_build_llm.return_value = MagicMock()
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(side_effect=capture_run_context)
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(task.id), skip_sandbox=True)

    assert len(captured_run_contexts) == 1
    run_ctx = captured_run_contexts[0]
    assert run_ctx.allowed_tools is not None
    assert "dispatch_subtask" in run_ctx.allowed_tools
    assert "gather_results" in run_ctx.allowed_tools


@pytest.mark.asyncio
async def test_supervisor_agent_with_existing_tools(db_session):
    """Verify supervisor tools are appended to existing allowed_tools."""
    from app.models.user import User
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    user = User(
        id=uuid.uuid4(),
        email=f"super2_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    # Task with some pre-existing allowed_tools
    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="coordinate with existing tools",
        status=TaskStatus.submitted, language="en",
        agent_role="supervisor",
        allowed_tools=["browser", "code_executor"],
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.commit()

    captured_run_contexts = []

    def capture_run_context(initial, config):
        run_ctx = config.get("configurable", {}).get("run_ctx")
        if run_ctx:
            captured_run_contexts.append(run_ctx)
        return {
            "result_summary": "done", "partial": False, "artifacts": []
        }

    with patch("app.orchestrator.runner.build_llm") as mock_build_llm, \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]):
        mock_build_llm.return_value = MagicMock()
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(side_effect=capture_run_context)
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(task.id), skip_sandbox=True)

    assert len(captured_run_contexts) == 1
    run_ctx = captured_run_contexts[0]
    assert run_ctx.allowed_tools is not None
    # Verify original tools are still there
    assert "browser" in run_ctx.allowed_tools
    assert "code_executor" in run_ctx.allowed_tools
    # Verify supervisor tools are added
    assert "dispatch_subtask" in run_ctx.allowed_tools
    assert "gather_results" in run_ctx.allowed_tools


@pytest.mark.asyncio
async def test_regular_agent_does_not_get_supervisor_tools(db_session):
    """Verify that non-supervisor agents do NOT have dispatch_subtask and gather_results injected."""
    from app.models.user import User
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    user = User(
        id=uuid.uuid4(),
        email=f"regular_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="do regular work",
        status=TaskStatus.submitted, language="en",
        agent_role=None,  # Not a supervisor
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.commit()

    captured_run_contexts = []

    def capture_run_context(initial, config):
        run_ctx = config.get("configurable", {}).get("run_ctx")
        if run_ctx:
            captured_run_contexts.append(run_ctx)
        return {
            "result_summary": "done", "partial": False, "artifacts": []
        }

    with patch("app.orchestrator.runner.build_llm") as mock_build_llm, \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]):
        mock_build_llm.return_value = MagicMock()
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(side_effect=capture_run_context)
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(task.id), skip_sandbox=True)

    assert len(captured_run_contexts) == 1
    run_ctx = captured_run_contexts[0]
    # Regular agents should NOT have supervisor tools
    if run_ctx.allowed_tools is not None:
        assert "dispatch_subtask" not in run_ctx.allowed_tools
        assert "gather_results" not in run_ctx.allowed_tools
