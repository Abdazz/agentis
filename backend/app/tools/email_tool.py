"""EmailTool — operator-enabled, HITL required before send (spec §6.4, Phase 3B)."""
from app.tools.base import BaseTool, SessionContext, ToolResult


async def _fetch_inbox(session: SessionContext, limit: int, filter_str=None) -> list[dict]:
    """IMAP fetch stub — full implementation requires credentials from UserIntegration."""
    return []


async def _search_emails(session: SessionContext, query: str) -> list[dict]:
    """IMAP search stub — full implementation requires credentials from UserIntegration."""
    return []


async def _send_email(
    session: SessionContext, to: list[str], subject: str, body: str, attachments=None
) -> dict:
    """SMTP send stub — full implementation requires credentials from UserIntegration."""
    return {"message_id": f"stub_{id(session)}"}


class EmailTool(BaseTool):
    name = "email"
    description = (
        "Send, read, and search emails via the user's configured email account. "
        "Requires HITL confirmation before sending. Operator must enable this tool."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["send", "read_inbox", "search"]},
            "to": {"type": "array", "items": {"type": "string"}},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "attachments": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "default": 20},
            "filter": {"type": "string"},
            "query": {"type": "string"},
            "hitl_approved": {"type": "boolean", "default": False},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action", "")
        hitl_approved = params.get("hitl_approved", False)

        if action == "send":
            if not hitl_approved:
                return ToolResult(
                    ok=False,
                    error="HITL required: email.send requires human confirmation before execution.",
                    data={
                        "hitl_required": True,
                        "action": "send",
                        "to": params.get("to"),
                        "subject": params.get("subject"),
                    },
                )
            data = await _send_email(
                session,
                to=params.get("to", []),
                subject=params.get("subject", ""),
                body=params.get("body", ""),
                attachments=params.get("attachments"),
            )
            return ToolResult(ok=True, data=data)

        elif action == "read_inbox":
            emails = await _fetch_inbox(
                session, limit=params.get("limit", 20), filter_str=params.get("filter")
            )
            return ToolResult(ok=True, data={"emails": emails})

        elif action == "search":
            emails = await _search_emails(session, query=params.get("query", ""))
            return ToolResult(ok=True, data={"emails": emails})

        else:
            return ToolResult(ok=False, error=f"Unknown action: {action!r}")
