"""Tests that runner.py picks up the per-org LLM override (BR-ADMIN-21)."""
import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_runner_uses_org_llm_provider(db_session):
    from app.models.user import User, UserRole
    from app.models.org import Organization, OrganizationMembership
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    org = Organization(
        id=uuid.uuid4(), name="GroqOrg",
        slug=f"groq-{uuid.uuid4().hex[:6]}",
        llm_provider="groq", llm_model="llama-3-70b", max_concurrent_tasks=5,
    )
    db_session.add(org)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        email=f"runner_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=org.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    db_session.add(OrganizationMembership(
        id=uuid.uuid4(), organization_id=org.id, user_id=user.id,
        role=UserRole.user, created_at=datetime.now(timezone.utc),
    ))

    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="test goal",
        status=TaskStatus.submitted, language="en",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.commit()

    captured_calls = []

    def mock_build_llm(**kwargs):
        captured_calls.append(kwargs)
        return MagicMock()

    with patch("app.orchestrator.runner.build_llm", side_effect=mock_build_llm), \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]):
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(return_value={
            "result_summary": "done", "partial": False, "artifacts": []
        })
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(task.id), skip_sandbox=True)

    assert len(captured_calls) == 1
    assert captured_calls[0].get("provider") == "groq"
    assert captured_calls[0].get("model") == "llama-3-70b"


@pytest.mark.asyncio
async def test_runner_uses_global_llm_when_no_org(db_session):
    from app.models.user import User
    from app.models.task import Task, TaskStatus
    from app.auth.password import hash_password

    user = User(
        id=uuid.uuid4(),
        email=f"noorg_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        active_organization_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()

    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="no-org task",
        status=TaskStatus.submitted, language="en",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.commit()

    captured_calls = []

    def mock_build_llm(**kwargs):
        captured_calls.append(kwargs)
        return MagicMock()

    with patch("app.orchestrator.runner.build_llm", side_effect=mock_build_llm), \
         patch("app.orchestrator.runner.sandbox_manager") as mock_sandbox, \
         patch("app.orchestrator.runner.build_graph") as mock_graph, \
         patch("app.orchestrator.runner.checkpointer_context") as mock_cp, \
         patch("app.orchestrator.runner.get_langfuse_callbacks", return_value=[]):
        mock_sandbox.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_graph.return_value.ainvoke = AsyncMock(return_value={
            "result_summary": "done", "partial": False, "artifacts": []
        })
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        from app.orchestrator.runner import run_task
        await run_task(str(task.id), skip_sandbox=True)

    assert len(captured_calls) == 1
    # No org = no override, provider and model should be None
    assert captured_calls[0].get("provider") is None
    assert captured_calls[0].get("model") is None
