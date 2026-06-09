import pytest
from unittest.mock import AsyncMock, patch
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="")


@pytest.mark.asyncio
async def test_email_send_requires_hitl(session):
    from app.tools.email_tool import EmailTool

    tool = EmailTool()
    result = await tool.execute(
        {"action": "send", "to": ["user@example.com"], "subject": "Hi", "body": "Hello"},
        session,
    )
    assert result.ok is False
    assert result.data.get("hitl_required") is True
    assert "send" in result.error.lower()


@pytest.mark.asyncio
async def test_email_read_inbox_executes_without_hitl(session):
    from app.tools.email_tool import EmailTool

    tool = EmailTool()

    with patch(
        "app.tools.email_tool._fetch_inbox",
        new=AsyncMock(
            return_value=[
                {
                    "id": "1",
                    "from": "a@b.com",
                    "subject": "Test",
                    "date": "2026-01-01",
                }
            ]
        ),
    ):
        result = await tool.execute({"action": "read_inbox", "limit": 5}, session)

    assert result.ok is True
    assert len(result.data["emails"]) == 1


@pytest.mark.asyncio
async def test_email_search_executes_without_hitl(session):
    from app.tools.email_tool import EmailTool

    tool = EmailTool()

    with patch(
        "app.tools.email_tool._search_emails", new=AsyncMock(return_value=[])
    ):
        result = await tool.execute({"action": "search", "query": "invoice"}, session)

    assert result.ok is True
    assert result.data["emails"] == []


@pytest.mark.asyncio
async def test_email_send_after_hitl_approval(session):
    from app.tools.email_tool import EmailTool

    tool = EmailTool()

    with patch(
        "app.tools.email_tool._send_email",
        new=AsyncMock(return_value={"message_id": "msg_123"}),
    ):
        result = await tool.execute(
            {
                "action": "send",
                "to": ["user@example.com"],
                "subject": "Hi",
                "body": "Hello",
                "hitl_approved": True,
            },
            session,
        )

    assert result.ok is True
    assert result.data["message_id"] == "msg_123"


@pytest.mark.asyncio
async def test_email_tool_unknown_action_returns_error(session):
    from app.tools.email_tool import EmailTool

    tool = EmailTool()
    result = await tool.execute({"action": "delete_all"}, session)
    assert result.ok is False
    assert "unknown action" in result.error.lower()
