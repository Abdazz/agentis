import pytest
from unittest.mock import AsyncMock, patch
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="")


@pytest.mark.asyncio
async def test_create_event_requires_hitl(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()
    result = await tool.execute(
        {"action": "create_event", "title": "Meeting", "start": "2026-06-10T10:00:00Z",
         "end": "2026-06-10T11:00:00Z"},
        session,
    )
    assert result.ok is False
    assert result.data.get("hitl_required") is True


@pytest.mark.asyncio
async def test_delete_event_requires_hitl(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()
    result = await tool.execute({"action": "delete_event", "event_id": "evt_1"}, session)
    assert result.ok is False
    assert result.data.get("hitl_required") is True


@pytest.mark.asyncio
async def test_list_events_executes_without_hitl(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()

    with patch("app.tools.calendar_tool._list_events",
               new=AsyncMock(return_value=[{"event_id": "e1", "title": "Standup", "start": "2026-06-10T09:00:00Z"}])):
        result = await tool.execute(
            {"action": "list_events", "date_from": "2026-06-01", "date_to": "2026-06-30"},
            session,
        )

    assert result.ok is True
    assert len(result.data["events"]) == 1


@pytest.mark.asyncio
async def test_create_event_after_hitl_approval(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()

    with patch("app.tools.calendar_tool._create_event",
               new=AsyncMock(return_value={"event_id": "evt_new"})):
        result = await tool.execute(
            {"action": "create_event", "title": "Meeting",
             "start": "2026-06-10T10:00:00Z", "end": "2026-06-10T11:00:00Z",
             "hitl_approved": True},
            session,
        )

    assert result.ok is True
    assert result.data["event_id"] == "evt_new"


@pytest.mark.asyncio
async def test_delete_event_after_hitl_approval(session):
    from app.tools.calendar_tool import CalendarTool
    tool = CalendarTool()

    with patch("app.tools.calendar_tool._delete_event",
               new=AsyncMock(return_value={"success": True})):
        result = await tool.execute(
            {"action": "delete_event", "event_id": "evt_1", "hitl_approved": True},
            session,
        )

    assert result.ok is True
    assert result.data["success"] is True
