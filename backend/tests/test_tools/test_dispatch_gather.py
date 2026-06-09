import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from app.tools.base import SessionContext


@pytest.mark.asyncio
async def test_dispatch_tool_creates_subtask():
    from app.tools.dispatch_tool import DispatchTool
    from app.models.task import Task

    parent_task_id = str(uuid.uuid4())
    parent_user_id = uuid.uuid4()

    # Mock parent task fetch
    mock_parent = MagicMock(spec=Task)
    mock_parent.id = uuid.UUID(parent_task_id)
    mock_parent.user_id = parent_user_id
    mock_parent.organization_id = None
    mock_parent.language = "en"
    mock_parent.max_iterations = 30

    # Mock database context
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_parent)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    session = SessionContext(
        session_id=parent_task_id,
        task_id=parent_task_id,
        sandbox_endpoint="",
    )

    mock_celery_task = MagicMock()
    mock_celery_task.delay = MagicMock()

    with patch("app.tools.dispatch_tool.AsyncSessionLocal") as mock_db_cls, \
         patch("app.tools.dispatch_tool.run_agent_task", mock_celery_task):
        mock_db_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        tool = DispatchTool()
        result = await tool.execute(
            {
                "goal": "research climate data",
                "agent_role": "research",
                "allowed_tools": ["web_search", "browser"],
            },
            session,
        )

    assert result.ok
    data = result.data
    assert "subtask_id" in data
    assert data["goal"] == "research climate data"
    assert data["agent_role"] == "research"

    # Verify Celery task was dispatched
    mock_celery_task.delay.assert_called_once_with(data["subtask_id"])
    # Verify db.add and db.commit were called
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_dispatch_tool_default_allowed_tools():
    from app.tools.dispatch_tool import DispatchTool
    from app.models.task import Task

    parent_task_id = str(uuid.uuid4())
    parent_user_id = uuid.uuid4()

    mock_parent = MagicMock(spec=Task)
    mock_parent.id = uuid.UUID(parent_task_id)
    mock_parent.user_id = parent_user_id
    mock_parent.organization_id = None
    mock_parent.language = "en"
    mock_parent.max_iterations = 30

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_parent)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    session = SessionContext(
        session_id=parent_task_id,
        task_id=parent_task_id,
        sandbox_endpoint="",
    )

    mock_celery_task = MagicMock()
    mock_celery_task.delay = MagicMock()

    with patch("app.tools.dispatch_tool.AsyncSessionLocal") as mock_db_cls, \
         patch("app.tools.dispatch_tool.run_agent_task", mock_celery_task):
        mock_db_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        tool = DispatchTool()
        result = await tool.execute(
            {
                "goal": "research climate data",
                "agent_role": "research",
            },
            session,
        )

    assert result.ok
    # Verify that the created child task received role-based tools
    # (By examining what was passed to db.add)
    added_task = mock_db.add.call_args[0][0]
    assert set(added_task.allowed_tools) == {"web_search", "browser", "http_caller"}


@pytest.mark.asyncio
async def test_dispatch_tool_analysis_role():
    from app.tools.dispatch_tool import DispatchTool
    from app.models.task import Task

    parent_task_id = str(uuid.uuid4())
    parent_user_id = uuid.uuid4()

    mock_parent = MagicMock(spec=Task)
    mock_parent.id = uuid.UUID(parent_task_id)
    mock_parent.user_id = parent_user_id
    mock_parent.organization_id = None
    mock_parent.language = "en"
    mock_parent.max_iterations = 30

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_parent)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    session = SessionContext(
        session_id=parent_task_id,
        task_id=parent_task_id,
        sandbox_endpoint="",
    )

    mock_celery_task = MagicMock()
    mock_celery_task.delay = MagicMock()

    with patch("app.tools.dispatch_tool.AsyncSessionLocal") as mock_db_cls, \
         patch("app.tools.dispatch_tool.run_agent_task", mock_celery_task):
        mock_db_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        tool = DispatchTool()
        result = await tool.execute(
            {
                "goal": "analyze the data",
                "agent_role": "analysis",
            },
            session,
        )

    assert result.ok
    added_task = mock_db.add.call_args[0][0]
    assert set(added_task.allowed_tools) == {"code_executor", "file_system"}


@pytest.mark.asyncio
async def test_gather_tool_empty_task_ids():
    from app.tools.gather_tool import GatherTool

    session = SessionContext(
        session_id="parent-1", task_id="parent-1", sandbox_endpoint=""
    )
    tool = GatherTool()
    result = await tool.execute({"task_ids": []}, session)
    assert result.ok
    assert result.data["results"] == []


@pytest.mark.asyncio
async def test_gather_tool_waits_for_results():
    from app.tools.gather_tool import GatherTool

    fake_bus = MagicMock()
    fake_bus.wait_for_all = AsyncMock(
        return_value=[
            {"subtask_id": "abc", "result": "research done"},
        ]
    )
    session = SessionContext(
        session_id="parent-1", task_id="parent-1", sandbox_endpoint=""
    )
    with patch("app.tools.gather_tool.get_agent_team_bus", return_value=fake_bus):
        tool = GatherTool()
        result = await tool.execute(
            {"task_ids": ["abc"], "timeout_seconds": 30},
            session,
        )
    assert result.ok
    assert len(result.data["results"]) == 1
    assert result.data["results"][0]["subtask_id"] == "abc"
    fake_bus.wait_for_all.assert_called_once_with(
        parent_task_id="parent-1",
        expected_count=1,
        timeout_seconds=30,
    )


@pytest.mark.asyncio
async def test_gather_tool_multiple_results():
    from app.tools.gather_tool import GatherTool

    fake_bus = MagicMock()
    fake_bus.wait_for_all = AsyncMock(
        return_value=[
            {"subtask_id": "abc", "result": "research done"},
            {"subtask_id": "def", "result": "analysis done"},
            {"subtask_id": "ghi", "result": "writing done"},
        ]
    )
    session = SessionContext(
        session_id="parent-1", task_id="parent-1", sandbox_endpoint=""
    )
    with patch("app.tools.gather_tool.get_agent_team_bus", return_value=fake_bus):
        tool = GatherTool()
        result = await tool.execute(
            {
                "task_ids": ["abc", "def", "ghi"],
                "timeout_seconds": 600,
            },
            session,
        )
    assert result.ok
    assert len(result.data["results"]) == 3
    fake_bus.wait_for_all.assert_called_once_with(
        parent_task_id="parent-1",
        expected_count=3,
        timeout_seconds=600,
    )


@pytest.mark.asyncio
async def test_gather_tool_default_timeout():
    from app.tools.gather_tool import GatherTool

    fake_bus = MagicMock()
    fake_bus.wait_for_all = AsyncMock(return_value=[])
    session = SessionContext(
        session_id="parent-1", task_id="parent-1", sandbox_endpoint=""
    )
    with patch("app.tools.gather_tool.get_agent_team_bus", return_value=fake_bus):
        tool = GatherTool()
        result = await tool.execute(
            {
                "task_ids": ["abc"],
            },
            session,
        )
    assert result.ok
    # Should use default timeout of 600 seconds
    fake_bus.wait_for_all.assert_called_once_with(
        parent_task_id="parent-1",
        expected_count=1,
        timeout_seconds=600,
    )
