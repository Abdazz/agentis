"""CalendarTool — operator-enabled, HITL required before create/delete
(spec §6.4, Phase 3B).

Uses generic CalDAV against the credentials the user configured via
POST /integrations (provider="caldav") — works with Nextcloud, Radicale,
Baïkal, SOGo, and any other CalDAV-compliant server (including Google
Calendar and Microsoft 365 via their CalDAV bridges), rather than
hard-coding one vendor's OAuth flow.

Expected credentials shape (see routers/integrations.py):
    {"url": "https://caldav.example.com/calendars/user/personal/",
     "username": "...", "password": "..."}
"""
import asyncio
from datetime import datetime

import caldav
import caldav.lib.error
import structlog

from app.database import AsyncSessionLocal
from app.services.integration_credentials import (
    get_integration_credentials, IntegrationNotConfigured,
)
from app.tools.base import BaseTool, SessionContext, ToolResult

log = structlog.get_logger()

PROVIDER = "caldav"


async def _get_credentials(user_id: str) -> dict | None:
    async with AsyncSessionLocal() as db:
        return await get_integration_credentials(db, user_id, PROVIDER)


def _calendar(creds: dict) -> caldav.Calendar:
    client = caldav.DAVClient(
        url=creds["url"], username=creds["username"], password=creds["password"], timeout=20,
    )
    return caldav.Calendar(client, url=creds["url"])


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _vevent_field(vevent, name: str) -> str | None:
    prop = vevent.get(name)
    if prop is None:
        return None
    return prop.dt.isoformat() if hasattr(prop, "dt") else str(prop)


def _list_events_sync(creds: dict, date_from: str, date_to: str) -> list[dict]:
    cal = _calendar(creds)
    results = cal.date_search(start=_parse_dt(date_from), end=_parse_dt(date_to))
    events = []
    for r in results:
        vevent = r.icalendar_component
        events.append({
            "event_id": str(vevent.get("uid", "")),
            "title": str(vevent.get("summary", "")),
            "start": _vevent_field(vevent, "dtstart"),
            "end": _vevent_field(vevent, "dtend"),
            "description": str(vevent.get("description", "")),
        })
    return events


def _create_event_sync(creds: dict, title: str, start: str, end: str,
                       attendees: list[str] | None, description: str | None) -> dict:
    cal = _calendar(creds)
    kwargs = {"dtstart": _parse_dt(start), "dtend": _parse_dt(end), "summary": title}
    if description:
        kwargs["description"] = description
    if attendees:
        kwargs["attendee"] = [
            a if a.lower().startswith("mailto:") else f"MAILTO:{a}" for a in attendees
        ]
    event = cal.add_event(**kwargs)
    uid = str(event.icalendar_component.get("uid", ""))
    return {"event_id": uid}


def _delete_event_sync(creds: dict, event_id: str) -> dict:
    cal = _calendar(creds)
    event = cal.event_by_uid(event_id)
    event.delete()
    return {"success": True}


async def _list_events(session: SessionContext, date_from: str, date_to: str) -> list[dict]:
    creds = await _get_credentials(session.user_id)
    if creds is None:
        return []
    return await asyncio.get_event_loop().run_in_executor(
        None, _list_events_sync, creds, date_from, date_to
    )


async def _create_event(session: SessionContext, title: str, start: str, end: str,
                        attendees, description) -> dict:
    creds = await _get_credentials(session.user_id)
    if creds is None:
        return {"error": "No calendar integration configured for this user"}
    return await asyncio.get_event_loop().run_in_executor(
        None, _create_event_sync, creds, title, start, end, attendees, description
    )


async def _delete_event(session: SessionContext, event_id: str) -> dict:
    creds = await _get_credentials(session.user_id)
    if creds is None:
        return {"error": "No calendar integration configured for this user"}
    return await asyncio.get_event_loop().run_in_executor(
        None, _delete_event_sync, creds, event_id
    )


class CalendarTool(BaseTool):
    name = "calendar"
    description = (
        "Manage calendar events via the user's configured CalDAV calendar "
        "(configured under Settings > Integrations): list events, create new events, "
        "and delete events. Requires HITL confirmation before creating or deleting. "
        "Operator must enable this tool."
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

        try:
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
                if "error" in data:
                    return ToolResult(ok=False, error=data["error"])
                return ToolResult(ok=True, data=data)

            elif action == "delete_event":
                data = await _delete_event(session, event_id=params.get("event_id", ""))
                if "error" in data:
                    return ToolResult(ok=False, error=data["error"])
                return ToolResult(ok=True, data=data)

            else:
                return ToolResult(ok=False, error=f"Unknown action: {action!r}")
        except caldav.lib.error.DAVError as e:
            return ToolResult(ok=False, error=f"CalDAV request failed: {e}", retryable=True)
        except (OSError, IntegrationNotConfigured) as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
