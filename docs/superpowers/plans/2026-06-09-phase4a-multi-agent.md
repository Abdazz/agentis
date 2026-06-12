# Phase 4A — Multi-Agent Collaboration Backend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a supervisor agent that decomposes goals into sub-goals, dispatches specialized child agents (research/analysis/writer), collects their results via Redis pub/sub, and aggregates a final report.

**Architecture:** The existing `run_task` runner is extended with a supervisor mode — when `task.agent_role == "supervisor"`, two extra tools (`dispatch_subtask`, `gather_results`) are injected into the ReAct loop. Child tasks are normal `Task` rows with `parent_task_id` and an `agent_role` column. A lightweight `AgentTeamBus` wraps aioredis pub/sub so the supervisor can subscribe to a channel and receive child completions instead of busy-polling.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Celery + Redis, SQLAlchemy async, pytest-asyncio

---

### Task 1: DB — `parent_task_id` + `agent_role` + migration

**Files:**
- Modify: `backend/app/models/task.py`
- Create: `backend/alembic/versions/f3a4b5c6d7e8_add_multi_agent_columns.py`
- Test: `backend/tests/test_models/test_task_multi_agent.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models/test_task_multi_agent.py
import pytest, uuid
from datetime import datetime, timezone
from app.models.task import Task, TaskStatus

@pytest.mark.asyncio
async def test_task_has_parent_task_id(db_session):
    parent = Task(
        id=uuid.uuid4(), user_id=uuid.uuid4(), goal="parent",
        status=TaskStatus.submitted,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(parent)
    await db_session.flush()
    child = Task(
        id=uuid.uuid4(), user_id=parent.user_id, goal="child",
        status=TaskStatus.submitted, parent_task_id=parent.id,
        agent_role="research",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(child)
    assert child.parent_task_id == parent.id
    assert child.agent_role == "research"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_models/test_task_multi_agent.py -v
```
Expected: FAIL — `Task` has no attribute `parent_task_id`

- [ ] **Step 3: Add columns to Task model**

In `backend/app/models/task.py`, add after `organization_id`:

```python
parent_task_id: Mapped[Optional[UUID]] = mapped_column(
    ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
)
agent_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
```

Also add to `__table_args__`:
```python
Index("idx_tasks_parent", "parent_task_id"),
```

- [ ] **Step 4: Create migration**

```python
# backend/alembic/versions/f3a4b5c6d7e8_add_multi_agent_columns.py
"""add multi-agent columns to tasks

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("parent_task_id", sa.UUID(), nullable=True))
    op.add_column("tasks", sa.Column("agent_role", sa.String(50), nullable=True))
    op.create_foreign_key(
        "fk_tasks_parent_task_id", "tasks",
        "tasks", ["parent_task_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_tasks_parent", "tasks", ["parent_task_id"])


def downgrade() -> None:
    op.drop_index("idx_tasks_parent", table_name="tasks")
    op.drop_constraint("fk_tasks_parent_task_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "agent_role")
    op.drop_column("tasks", "parent_task_id")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && python3 -m pytest tests/test_models/test_task_multi_agent.py -v
```
Expected: PASS

- [ ] **Step 6: Run full suite**

```bash
cd backend && python3 -m pytest tests/ -x --tb=short -q 2>&1 | tail -5
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/task.py backend/alembic/versions/f3a4b5c6d7e8_add_multi_agent_columns.py backend/tests/test_models/test_task_multi_agent.py
git commit -m "feat(4a): add parent_task_id + agent_role columns to Task"
```

---

### Task 2: `AgentTeamBus` — Redis pub/sub inter-agent message bus

**Files:**
- Create: `backend/app/services/agent_team_bus.py`
- Test: `backend/tests/test_services/test_agent_team_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_services/test_agent_team_bus.py
import pytest, asyncio, json
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_publish_sends_to_channel():
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock(return_value=1)
    with patch("app.services.agent_team_bus.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = fake_redis
        from app.services.agent_team_bus import AgentTeamBus
        bus = AgentTeamBus(redis_url="redis://localhost:6379/1")
        await bus.publish("parent-123", {"subtask_id": "child-456", "result": "done"})
    fake_redis.publish.assert_called_once()
    channel, payload = fake_redis.publish.call_args[0]
    assert channel == "agent_team:parent-123"
    assert json.loads(payload)["subtask_id"] == "child-456"


@pytest.mark.asyncio
async def test_wait_for_all_returns_results_when_all_done():
    """wait_for_all collects N messages from the channel within timeout."""
    messages = [
        MagicMock(data=json.dumps({"subtask_id": f"child-{i}", "result": f"res-{i}"}).encode())
        for i in range(2)
    ]
    fake_pubsub = MagicMock()
    fake_pubsub.subscribe = AsyncMock()
    fake_pubsub.unsubscribe = AsyncMock()
    fake_pubsub.__aiter__ = MagicMock(return_value=iter(messages))
    fake_redis = MagicMock()
    fake_redis.pubsub.return_value = fake_pubsub
    with patch("app.services.agent_team_bus.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = fake_redis
        from importlib import reload
        import app.services.agent_team_bus as m
        reload(m)
        bus = m.AgentTeamBus(redis_url="redis://localhost:6379/1")
        results = await bus.wait_for_all(
            parent_task_id="parent-123",
            expected_count=2,
            timeout_seconds=5,
        )
    assert len(results) == 2
    assert results[0]["subtask_id"] == "child-0"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_services/test_agent_team_bus.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: Implement AgentTeamBus**

```python
# backend/app/services/agent_team_bus.py
"""Redis pub/sub message bus for inter-agent communication (spec §13.2)."""
import asyncio
import json
import structlog
from typing import Any

log = structlog.get_logger()

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None  # type: ignore


class AgentTeamBus:
    """Publish sub-task results and subscribe to collect them."""

    def __init__(self, redis_url: str) -> None:
        if aioredis is None:
            raise RuntimeError("redis package not installed")
        self._redis = aioredis.from_url(redis_url, decode_responses=False)

    def _channel(self, parent_task_id: str) -> str:
        return f"agent_team:{parent_task_id}"

    async def publish(self, parent_task_id: str, message: dict[str, Any]) -> None:
        await self._redis.publish(self._channel(parent_task_id), json.dumps(message))

    async def wait_for_all(
        self,
        parent_task_id: str,
        expected_count: int,
        timeout_seconds: int = 600,
    ) -> list[dict[str, Any]]:
        """Block until `expected_count` messages arrive or timeout. Returns collected results."""
        channel = self._channel(parent_task_id)
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        results: list[dict[str, Any]] = []
        try:
            async def _collect():
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    try:
                        results.append(json.loads(msg["data"]))
                    except (json.JSONDecodeError, KeyError):
                        pass
                    if len(results) >= expected_count:
                        break

            await asyncio.wait_for(_collect(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            log.warning("agent_team_bus_timeout", parent=parent_task_id, got=len(results), expected=expected_count)
        finally:
            await pubsub.unsubscribe(channel)
        return results


_bus: AgentTeamBus | None = None


def get_agent_team_bus() -> AgentTeamBus:
    global _bus
    if _bus is None:
        from app.config import settings
        _bus = AgentTeamBus(redis_url=settings.redis_cache_url)
    return _bus
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python3 -m pytest tests/test_services/test_agent_team_bus.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agent_team_bus.py backend/tests/test_services/test_agent_team_bus.py
git commit -m "feat(4a): AgentTeamBus — Redis pub/sub inter-agent message bus"
```

---

### Task 3: `DispatchTool` + `GatherTool` for the supervisor

**Files:**
- Create: `backend/app/tools/dispatch_tool.py`
- Create: `backend/app/tools/gather_tool.py`
- Modify: `backend/app/tools/init_registry.py` (add to `_BUILTIN_TOOLS`)
- Test: `backend/tests/test_tools/test_dispatch_gather.py`

The `DispatchTool` creates a child `Task` row + fires a Celery job. `GatherTool` calls `AgentTeamBus.wait_for_all()` to collect results once all children have reported.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_tools/test_dispatch_gather.py
import pytest, uuid
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone
from app.tools.base import SessionContext


@pytest.mark.asyncio
async def test_dispatch_tool_creates_subtask(db_session):
    from app.tools.dispatch_tool import DispatchTool
    from app.models.task import Task, TaskStatus
    from app.models.user import User
    from app.auth.password import hash_password
    from sqlalchemy import select

    user = User(
        id=uuid.uuid4(), email=f"dt_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    parent_task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="parent goal",
        status=TaskStatus.running, agent_role="supervisor",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(parent_task)
    await db_session.commit()

    session = SessionContext(
        session_id=str(parent_task.id),
        task_id=str(parent_task.id),
        sandbox_endpoint="",
    )
    # Patch celery task to avoid actual dispatch
    with patch("app.tools.dispatch_tool.run_agent_task") as mock_celery:
        mock_celery.delay = MagicMock()
        tool = DispatchTool()
        result = await tool.execute(
            {"goal": "research climate data", "agent_role": "research",
             "allowed_tools": ["web_search", "browser"]},
            session,
        )
    assert result.ok
    data = result.data
    assert "subtask_id" in data
    # Verify task was created in DB
    row = await db_session.get(Task, uuid.UUID(data["subtask_id"]))
    assert row is not None
    assert row.parent_task_id == parent_task.id
    assert row.agent_role == "research"


@pytest.mark.asyncio
async def test_gather_tool_waits_for_results():
    from app.tools.gather_tool import GatherTool
    from app.tools.base import SessionContext
    fake_bus = MagicMock()
    fake_bus.wait_for_all = AsyncMock(return_value=[
        {"subtask_id": "abc", "result": "research done"},
    ])
    session = SessionContext(session_id="parent-1", task_id="parent-1", sandbox_endpoint="")
    with patch("app.tools.gather_tool.get_agent_team_bus", return_value=fake_bus):
        tool = GatherTool()
        result = await tool.execute(
            {"task_ids": ["abc"], "timeout_seconds": 30},
            session,
        )
    assert result.ok
    assert len(result.data["results"]) == 1
    fake_bus.wait_for_all.assert_called_once_with(
        parent_task_id="parent-1", expected_count=1, timeout_seconds=30,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python3 -m pytest tests/test_tools/test_dispatch_gather.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement DispatchTool**

```python
# backend/app/tools/dispatch_tool.py
"""Dispatch a specialized child agent task (supervisor tool, Phase 4A)."""
from app.tools.base import BaseTool, ToolResult, SessionContext


class DispatchTool(BaseTool):
    name = "dispatch_subtask"
    description = (
        "Spawn a specialized child agent to handle a sub-goal. "
        "Returns the subtask_id; call gather_results when all children are dispatched."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "The sub-goal for this agent"},
            "agent_role": {
                "type": "string",
                "enum": ["research", "analysis", "writer"],
                "description": "Specialized role that determines available tools",
            },
            "allowed_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tool names this child agent may use",
            },
        },
        "required": ["goal", "agent_role"],
    }

    # Tool sets per role (defaults if caller doesn't specify)
    _ROLE_TOOLS: dict[str, list[str]] = {
        "research": ["web_search", "browser", "http_caller"],
        "analysis": ["code_executor", "file_system"],
        "writer": ["file_system", "doc_parser"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        import uuid
        from datetime import datetime, timezone
        from app.database import AsyncSessionLocal
        from app.models.task import Task, TaskStatus
        from app.worker.tasks import run_agent_task

        goal = params.get("goal", "")
        agent_role = params.get("agent_role", "research")
        allowed_tools = params.get("allowed_tools") or self._ROLE_TOOLS.get(agent_role, [])
        parent_task_id = uuid.UUID(session.task_id)

        async with AsyncSessionLocal() as db:
            parent = await db.get(Task, parent_task_id)
            child = Task(
                id=uuid.uuid4(),
                user_id=parent.user_id,
                organization_id=parent.organization_id,
                goal=goal,
                status=TaskStatus.submitted,
                language=parent.language,
                parent_task_id=parent_task_id,
                agent_role=agent_role,
                allowed_tools=allowed_tools,
                max_iterations=parent.max_iterations,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(child)
            await db.commit()
            subtask_id = str(child.id)

        run_agent_task.delay(subtask_id)
        return ToolResult(ok=True, data={"subtask_id": subtask_id, "goal": goal, "agent_role": agent_role})
```

- [ ] **Step 4: Implement GatherTool**

```python
# backend/app/tools/gather_tool.py
"""Gather results from dispatched sub-agents via the AgentTeamBus (Phase 4A)."""
from app.tools.base import BaseTool, ToolResult, SessionContext
from app.services.agent_team_bus import get_agent_team_bus


class GatherTool(BaseTool):
    name = "gather_results"
    description = (
        "Wait for all dispatched child agents to complete and collect their results. "
        "Pass the list of subtask_ids returned by dispatch_subtask calls."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of subtask_ids to wait for",
            },
            "timeout_seconds": {
                "type": "integer",
                "default": 600,
                "description": "Max seconds to wait before giving up",
            },
        },
        "required": ["task_ids"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        task_ids: list[str] = params.get("task_ids", [])
        timeout: int = params.get("timeout_seconds", 600)
        if not task_ids:
            return ToolResult(ok=True, data={"results": []})
        bus = get_agent_team_bus()
        results = await bus.wait_for_all(
            parent_task_id=session.task_id,
            expected_count=len(task_ids),
            timeout_seconds=timeout,
        )
        return ToolResult(ok=True, data={"results": results})
```

- [ ] **Step 5: Add to _BUILTIN_TOOLS in init_registry.py**

In `backend/app/tools/init_registry.py`, import and add to `_BUILTIN_TOOLS`:

```python
from app.tools.dispatch_tool import DispatchTool
from app.tools.gather_tool import GatherTool
```

And add `DispatchTool, GatherTool` to `_BUILTIN_TOOLS` list.

- [ ] **Step 6: Run tests**

```bash
cd backend && python3 -m pytest tests/test_tools/test_dispatch_gather.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/tools/dispatch_tool.py backend/app/tools/gather_tool.py backend/app/tools/init_registry.py backend/tests/test_tools/test_dispatch_gather.py
git commit -m "feat(4a): DispatchTool + GatherTool — supervisor spawns and collects child agents"
```

---

### Task 4: Runner — publish child result to parent bus on completion

**Files:**
- Modify: `backend/app/orchestrator/runner.py`
- Test: `backend/tests/test_orchestrator/test_runner_multi_agent.py`

When a child task (one with `parent_task_id`) completes, its runner publishes `{subtask_id, result, status}` to the parent's `agent_team:{parent_task_id}` channel.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_orchestrator/test_runner_multi_agent.py
import pytest, uuid
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.auth.password import hash_password


@pytest.mark.asyncio
async def test_child_runner_publishes_result_on_complete(db_session):
    """When a child task completes, it publishes its result to the parent bus channel."""
    user = User(
        id=uuid.uuid4(), email=f"mr_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    parent_id = uuid.uuid4()
    parent = Task(
        id=parent_id, user_id=user.id, goal="parent",
        status=TaskStatus.running, agent_role="supervisor",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(parent)
    child = Task(
        id=uuid.uuid4(), user_id=user.id, goal="child goal",
        status=TaskStatus.submitted, parent_task_id=parent_id, agent_role="research",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(child)
    await db_session.commit()

    fake_bus = MagicMock()
    fake_bus.publish = AsyncMock()
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="research done", tool_calls=[]))
    fake_llm.bind_tools = MagicMock(return_value=fake_llm)

    with (
        patch("app.orchestrator.runner.sandbox_manager") as mock_sm,
        patch("app.orchestrator.runner.get_agent_team_bus", return_value=fake_bus),
        patch("app.orchestrator.graph.AsyncPostgresSaver") as mock_cp,
        patch("app.orchestrator.graph.AsyncConnectionPool") as mock_pool,
    ):
        mock_sm.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_sm.destroy_session = MagicMock()
        mock_cp.return_value.setup = AsyncMock()
        mock_pool.return_value.__aenter__ = AsyncMock(return_value=mock_pool.return_value)
        mock_pool.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=mock_cp.return_value)
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.orchestrator.runner import run_task
        await run_task(str(child.id), llm=fake_llm, skip_sandbox=True)

    fake_bus.publish.assert_called_once()
    call_args = fake_bus.publish.call_args
    assert call_args[0][0] == str(parent_id)
    payload = call_args[0][1]
    assert payload["subtask_id"] == str(child.id)
    assert payload["status"] == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_orchestrator/test_runner_multi_agent.py -v
```
Expected: FAIL

- [ ] **Step 3: Add bus publish at end of run_task**

In `backend/app/orchestrator/runner.py`, after the `record_usage` commit block and before `await _set_status(task_id, TaskStatus.completed, ...)`:

Add import at the top of the function body:
```python
from app.services.agent_team_bus import get_agent_team_bus
```

After the `_set_status(task_id, TaskStatus.completed, ...)` call, add:

```python
        # If this is a child task, notify the supervisor via the message bus (Phase 4A)
        if task.parent_task_id is not None:
            try:
                bus = get_agent_team_bus()
                await bus.publish(str(task.parent_task_id), {
                    "subtask_id": task_id_str,
                    "status": "completed",
                    "result": summary,
                })
            except Exception:
                log.warning("agent_bus_publish_failed", task_id=task_id_str)
```

The `task` variable is already set at the top of `run_task`; we need to keep a reference. Since the DB session closes before the try/except block, load `parent_task_id` from the task into a local var:

```python
        parent_task_id = task.parent_task_id  # loaded in the first async with block
```

Add this line right after `allowed_tools = task.allowed_tools` in the first DB block.

- [ ] **Step 4: Run test**

```bash
cd backend && python3 -m pytest tests/test_orchestrator/test_runner_multi_agent.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/runner.py backend/tests/test_orchestrator/test_runner_multi_agent.py
git commit -m "feat(4a): runner publishes child result to parent bus on completion"
```

---

### Task 5: `GET /tasks/{id}/subtasks` endpoint

**Files:**
- Modify: `backend/app/routers/tasks.py`
- Modify: `backend/app/schemas/task.py` (add `parent_task_id`, `agent_role` to `TaskResponse`; add `SubtaskListResponse`)
- Test: `backend/tests/test_routers/test_subtasks.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_routers/test_subtasks.py
import pytest, uuid
from httpx import AsyncClient
from datetime import datetime, timezone
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.auth.password import hash_password


@pytest.mark.asyncio
async def test_list_subtasks_returns_children(async_client: AsyncClient, db_session):
    user = User(
        id=uuid.uuid4(), email=f"st_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    parent = Task(
        id=uuid.uuid4(), user_id=user.id, goal="parent goal",
        status=TaskStatus.running, agent_role="supervisor",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(parent)
    await db_session.flush()
    child = Task(
        id=uuid.uuid4(), user_id=user.id, goal="child goal",
        status=TaskStatus.completed, parent_task_id=parent.id, agent_role="research",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(child)
    await db_session.commit()

    login = await async_client.post("/api/v1/auth/login",
                                    json={"email": user.email, "password": "Pass1234!Secret"})
    # Register first if needed
    if login.status_code == 401:
        await async_client.post("/api/v1/auth/register",
                                json={"email": user.email, "password": "Pass1234!Secret"})
        login = await async_client.post("/api/v1/auth/login",
                                        json={"email": user.email, "password": "Pass1234!Secret"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = await async_client.get(f"/api/v1/tasks/{parent.id}/subtasks", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(s["id"] == str(child.id) for s in data)
    assert any(s["agent_role"] == "research" for s in data)


@pytest.mark.asyncio
async def test_list_subtasks_returns_empty_for_non_supervisor(async_client: AsyncClient, db_session):
    """A task with no children returns an empty list."""
    reg = await async_client.post("/api/v1/auth/register",
                                  json={"email": f"st_{uuid.uuid4().hex[:6]}@test.com",
                                        "password": "Pass1234!Secret"})
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Create a plain task
    task_resp = await async_client.post("/api/v1/tasks",
                                        json={"goal": "single agent task"},
                                        headers=headers)
    task_id = task_resp.json()["id"]
    resp = await async_client.get(f"/api/v1/tasks/{task_id}/subtasks", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_subtasks_rejects_other_user(async_client: AsyncClient, db_session):
    """IDOR: user B cannot list user A's task's subtasks."""
    reg_a = await async_client.post("/api/v1/auth/register",
                                    json={"email": f"a_{uuid.uuid4().hex[:6]}@test.com",
                                          "password": "Pass1234!Secret"})
    token_a = reg_a.json()["access_token"]
    task_resp = await async_client.post("/api/v1/tasks",
                                        json={"goal": "private task"},
                                        headers={"Authorization": f"Bearer {token_a}"})
    task_id = task_resp.json()["id"]

    reg_b = await async_client.post("/api/v1/auth/register",
                                    json={"email": f"b_{uuid.uuid4().hex[:6]}@test.com",
                                          "password": "Pass1234!Secret"})
    token_b = reg_b.json()["access_token"]
    resp = await async_client.get(f"/api/v1/tasks/{task_id}/subtasks",
                                  headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python3 -m pytest tests/test_routers/test_subtasks.py -v
```
Expected: FAIL

- [ ] **Step 3: Add `parent_task_id` and `agent_role` to `TaskResponse` schema**

In `backend/app/schemas/task.py`, add to `TaskResponse`:

```python
parent_task_id: Optional[uuid.UUID] = None
agent_role: Optional[str] = None
```

- [ ] **Step 4: Add `GET /tasks/{id}/subtasks` endpoint**

In `backend/app/routers/tasks.py`, add after the existing task detail endpoint:

```python
@router.get("/{task_id}/subtasks", response_model=list[TaskResponse])
async def list_subtasks(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Task]:
    """Return all child tasks belonging to the given supervisor task."""
    # Ownership check
    parent = await db.get(Task, task_id)
    if parent is None or parent.deleted_at is not None or parent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await db.execute(
        select(Task).where(
            Task.parent_task_id == task_id,
            Task.deleted_at.is_(None),
        ).order_by(Task.created_at)
    )
    return list(result.scalars().all())
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python3 -m pytest tests/test_routers/test_subtasks.py -v
```
Expected: PASS

- [ ] **Step 6: Run full suite**

```bash
cd backend && python3 -m pytest tests/ -x --tb=short -q 2>&1 | tail -5
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/tasks.py backend/app/schemas/task.py backend/tests/test_routers/test_subtasks.py
git commit -m "feat(4a): GET /tasks/{id}/subtasks + parent_task_id/agent_role in TaskResponse"
```

---

### Task 6: Runner — supervisor mode injects DispatchTool + GatherTool

**Files:**
- Modify: `backend/app/orchestrator/runner.py`
- Test: `backend/tests/test_orchestrator/test_runner_supervisor.py`

When `task.agent_role == "supervisor"`, the runner injects `dispatch_subtask` and `gather_results` into the `allowed_tools` list passed to `RunContext`, so the LangGraph ReAct loop can call them.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_orchestrator/test_runner_supervisor.py
import pytest, uuid
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.auth.password import hash_password


@pytest.mark.asyncio
async def test_supervisor_task_includes_dispatch_gather_tools(db_session):
    """RunContext.allowed_tools includes dispatch_subtask and gather_results for supervisor tasks."""
    user = User(
        id=uuid.uuid4(), email=f"sv_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="coordinate agents",
        status=TaskStatus.submitted, agent_role="supervisor",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.commit()

    captured_ctx = {}
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="done", tool_calls=[]))
    fake_llm.bind_tools = MagicMock(return_value=fake_llm)

    original_build = None

    async def mock_ainvoke(initial, config=None):
        captured_ctx["run_ctx"] = config["configurable"]["run_ctx"]
        return {**initial, "done": True, "result_summary": "ok", "partial": False, "artifacts": []}

    with (
        patch("app.orchestrator.runner.sandbox_manager") as mock_sm,
        patch("app.orchestrator.runner.get_agent_team_bus", return_value=MagicMock(publish=AsyncMock())),
        patch("app.orchestrator.graph.AsyncPostgresSaver") as mock_cp,
        patch("app.orchestrator.graph.AsyncConnectionPool") as mock_pool,
    ):
        mock_sm.create_session = AsyncMock(return_value=MagicMock(endpoint=""))
        mock_sm.destroy_session = MagicMock()
        mock_cp.return_value.setup = AsyncMock()
        mock_pool.return_value.__aenter__ = AsyncMock(return_value=mock_pool.return_value)
        mock_pool.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_cp.return_value.__aenter__ = AsyncMock(return_value=mock_cp.return_value)
        mock_cp.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("app.orchestrator.graph.StateGraph") as mock_sg:
            mock_graph = MagicMock()
            mock_graph.ainvoke = mock_ainvoke
            mock_sg.return_value.compile.return_value = mock_graph
            mock_sg.return_value.add_node = MagicMock()
            mock_sg.return_value.set_entry_point = MagicMock()
            mock_sg.return_value.add_edge = MagicMock()
            mock_sg.return_value.add_conditional_edges = MagicMock()

            from app.orchestrator.runner import run_task
            await run_task(str(task.id), llm=fake_llm, skip_sandbox=True)

    run_ctx = captured_ctx.get("run_ctx")
    assert run_ctx is not None
    allowed = run_ctx.allowed_tools or []
    assert "dispatch_subtask" in allowed
    assert "gather_results" in allowed
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_orchestrator/test_runner_supervisor.py -v
```
Expected: FAIL

- [ ] **Step 3: Inject supervisor tools in runner.py**

In `backend/app/orchestrator/runner.py`, after building `allowed_tools` (line where `allowed_tools = task.allowed_tools`), add:

```python
        # Supervisor agents always have access to dispatch and gather tools (BR-MULTI-01)
        if task.agent_role == "supervisor":
            supervisor_tools = ["dispatch_subtask", "gather_results"]
            if allowed_tools is None:
                allowed_tools = supervisor_tools
            else:
                allowed_tools = list(allowed_tools) + supervisor_tools
```

- [ ] **Step 4: Run test**

```bash
cd backend && python3 -m pytest tests/test_orchestrator/test_runner_supervisor.py -v
```
Expected: PASS

- [ ] **Step 5: Run full suite**

```bash
cd backend && python3 -m pytest tests/ -x --tb=short -q 2>&1 | tail -5
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/orchestrator/runner.py backend/tests/test_orchestrator/test_runner_supervisor.py
git commit -m "feat(4a): inject dispatch_subtask + gather_results into supervisor RunContext"
```
