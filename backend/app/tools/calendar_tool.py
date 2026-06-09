"""CalendarTool — operator-enabled, HITL required before create/delete (spec §6.4, Phase 3B)."""
from app.tools.base import BaseTool, SessionContext, ToolResult


async def _list_events(session: SessionContext, date_from: str, date_to: str) -> list[dict]:
    """CalDAV/API list events stub."""
    return []


async def _create_event(session: SessionContext, title: str, start: str, end: str,
                        attendees, description) -> dict:
    """CalDAV/API create event stub."""
    return {"event_id": f"stub_{id(session)}"}


async def _delete_event(session: SessionContext, event_id: str) -> dict:
    """CalDAV/API delete event stub."""
    return {"success": True}


class CalendarTool(BaseTool):
    name = "calendar"
    description = (
        "Manage calendar events: list events, create new events, and delete events. "
        "Requires HITL confirmation before creating or deleting. Operator must enable this tool."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create_event", "list_events", "delete_event"]},
            "title": {"type": "string"},
            "start": {"type": "string", "description": "ISO 8601 datetime"},
            "end": {"type": "string", "description": "ISO 8601 datetime"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "description": {"type": "string"},
            "date_from": {"type": "string", "description": "ISO 8601 date"},
            "date_to": {"type": "string", "description": "ISO 8601 date"},
            "event_id": {"type": "string"},
            "hitl_approved": {"type": "boolean", "default": False},
        },
        "required": ["action"],
    }

    _HITL_ACTIONS = {"create_event", "delete_event"}

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action", "")
        hitl_approved = params.get("hitl_approved", False)

        if action in self._HITL_ACTIONS and not hitl_approved:
            return ToolResult(
                ok=False,
                error=f"HITL required: calendar.{action} requires human confirmation before execution.",
                data={"hitl_required": True, "action": action,
                      "title": params.get("title"), "event_id": params.get("event_id")},
            )

        if action == "list_events":
            events = await _list_events(
                session,
                date_from=params.get("date_from", ""),
                date_to=params.get("date_to", ""),
            )
            return ToolResult(ok=True, data={"events": events})

        elif action == "create_event":
            data = await _create_event(
                session,
                title=params.get("title", ""),
                start=params.get("start", ""),
                end=params.get("end", ""),
                attendees=params.get("attendees"),
                description=params.get("description"),
            )
            return ToolResult(ok=True, data=data)

        elif action == "delete_event":
            data = await _delete_event(session, event_id=params.get("event_id", ""))
            return ToolResult(ok=True, data=data)

        else:
            return ToolResult(ok=False, error=f"Unknown action: {action!r}")
