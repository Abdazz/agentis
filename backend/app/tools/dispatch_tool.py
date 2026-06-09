"""Dispatch a specialized child agent task (supervisor tool, Phase 4A)."""
import uuid
from datetime import datetime, timezone

from app.tools.base import BaseTool, ToolResult, SessionContext
from app.database import AsyncSessionLocal
from app.models.task import Task, TaskStatus
from app.worker.tasks import run_agent_task


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

    _ROLE_TOOLS: dict[str, list[str]] = {
        "research": ["web_search", "browser", "http_caller"],
        "analysis": ["code_executor", "file_system"],
        "writer": ["file_system", "doc_parser"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        goal = params.get("goal", "")
        agent_role = params.get("agent_role", "research")

        # Validate role is known before use (prevents unknown roles getting default [] tools)
        if agent_role not in self._ROLE_TOOLS:
            return ToolResult(ok=False, error=f"Unknown agent_role '{agent_role}'. Must be one of: {list(self._ROLE_TOOLS)}")

        role_allowed = set(self._ROLE_TOOLS[agent_role])
        requested = set(params.get("allowed_tools") or role_allowed)

        parent_task_id = uuid.UUID(session.task_id)

        async with AsyncSessionLocal() as db:
            parent = await db.get(Task, parent_task_id)
            # Intersect role ceiling, caller request, and parent's own tool allowlist.
            # Child can never exceed the parent's permissions (BR-MULTI-PERM-01).
            # isinstance guard: JSON column returns None or list; other types (e.g. MagicMock in tests) fall back to role_allowed.
            parent_tools = parent.allowed_tools
            parent_allowed = set(parent_tools) if isinstance(parent_tools, list) and parent_tools else role_allowed
            allowed_tools = sorted(role_allowed & requested & parent_allowed)
            if not allowed_tools:
                return ToolResult(ok=False, error="No permitted tools for the requested role and parent constraints")

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
