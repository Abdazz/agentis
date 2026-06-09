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
