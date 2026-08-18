import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


# --- Real CalDAV wiring (credentials -> caldav library) ---

@pytest.fixture
def creds():
    return {"url": "https://caldav.example.com/cal/", "username": "me", "password": "secret"}


class _FakeProp:
    def __init__(self, value):
        self.dt = value

    def __str__(self):
        return str(self.dt)


class _FakeVevent:
    def __init__(self, fields: dict):
        self._fields = fields

    def get(self, key, default=""):
        return self._fields.get(key, default)


@pytest.mark.asyncio
async def test_list_events_returns_empty_when_no_integration_configured(session):
    from app.tools.calendar_tool import _list_events
    with patch("app.tools.calendar_tool._get_credentials", new=AsyncMock(return_value=None)):
        result = await _list_events(session, "2026-06-01", "2026-06-30")
    assert result == []


@pytest.mark.asyncio
async def test_list_events_maps_caldav_results(session, creds):
    from app.tools.calendar_tool import _list_events

    fake_result = MagicMock()
    from datetime import datetime
    fake_result.icalendar_component = _FakeVevent({
        "uid": "evt-uid-1", "summary": "Standup",
        "dtstart": _FakeProp(datetime(2026, 6, 10, 9, 0, 0)),
        "dtend": _FakeProp(datetime(2026, 6, 10, 9, 15, 0)),
        "description": "Daily sync",
    })
    mock_cal = MagicMock()
    mock_cal.date_search.return_value = [fake_result]

    with patch("app.tools.calendar_tool._get_credentials", new=AsyncMock(return_value=creds)), \
         patch("app.tools.calendar_tool._calendar", return_value=mock_cal):
        result = await _list_events(session, "2026-06-01T00:00:00", "2026-06-30T00:00:00")

    assert len(result) == 1
    assert result[0]["event_id"] == "evt-uid-1"
    assert result[0]["title"] == "Standup"


@pytest.mark.asyncio
async def test_create_event_returns_error_when_no_integration_configured(session):
    from app.tools.calendar_tool import _create_event
    with patch("app.tools.calendar_tool._get_credentials", new=AsyncMock(return_value=None)):
        result = await _create_event(session, "Meeting", "2026-06-10T10:00:00",
                                     "2026-06-10T11:00:00", None, None)
    assert "error" in result


@pytest.mark.asyncio
async def test_create_event_calls_caldav_add_event(session, creds):
    from app.tools.calendar_tool import _create_event

    fake_event = MagicMock()
    fake_event.icalendar_component = _FakeVevent({"uid": "new-uid"})
    mock_cal = MagicMock()
    mock_cal.add_event.return_value = fake_event

    with patch("app.tools.calendar_tool._get_credentials", new=AsyncMock(return_value=creds)), \
         patch("app.tools.calendar_tool._calendar", return_value=mock_cal):
        result = await _create_event(session, "Meeting", "2026-06-10T10:00:00",
                                      "2026-06-10T11:00:00", ["a@b.com"], "Discuss roadmap")

    assert result == {"event_id": "new-uid"}
    call_kwargs = mock_cal.add_event.call_args.kwargs
    assert call_kwargs["summary"] == "Meeting"
    assert call_kwargs["description"] == "Discuss roadmap"
    assert call_kwargs["attendee"] == ["MAILTO:a@b.com"]


@pytest.mark.asyncio
async def test_delete_event_calls_caldav_event_by_uid_and_delete(session, creds):
    from app.tools.calendar_tool import _delete_event

    fake_event = MagicMock()
    mock_cal = MagicMock()
    mock_cal.event_by_uid.return_value = fake_event

    with patch("app.tools.calendar_tool._get_credentials", new=AsyncMock(return_value=creds)), \
         patch("app.tools.calendar_tool._calendar", return_value=mock_cal):
        result = await _delete_event(session, "evt-1")

    mock_cal.event_by_uid.assert_called_once_with("evt-1")
    fake_event.delete.assert_called_once()
    assert result == {"success": True}


@pytest.mark.asyncio
async def test_execute_create_event_wraps_daverror_as_retryable_tool_error(session, creds):
    import caldav.lib.error
    from app.tools.calendar_tool import CalendarTool

    tool = CalendarTool()
    with patch("app.tools.calendar_tool._get_credentials", new=AsyncMock(return_value=creds)), \
         patch("app.tools.calendar_tool._calendar",
               side_effect=caldav.lib.error.DAVError("server unreachable")):
        result = await tool.execute(
            {"action": "create_event", "title": "M", "start": "2026-06-10T10:00:00",
             "end": "2026-06-10T11:00:00", "hitl_approved": True},
            session,
        )

    assert result.ok is False
    assert result.retryable is True
