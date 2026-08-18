import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


# --- Real IMAP/SMTP wiring (credentials -> imaplib/smtplib) ---

@pytest.fixture
def creds():
    return {
        "username": "me@example.com", "password": "secret",
        "imap_host": "imap.example.com", "imap_port": 993,
        "smtp_host": "smtp.example.com", "smtp_port": 587,
    }


@pytest.mark.asyncio
async def test_fetch_inbox_returns_empty_when_no_integration_configured(session):
    from app.tools.email_tool import _fetch_inbox
    with patch("app.tools.email_tool._get_credentials", new=AsyncMock(return_value=None)):
        result = await _fetch_inbox(session, limit=10)
    assert result == []


@pytest.mark.asyncio
async def test_fetch_inbox_parses_imap_messages(session, creds):
    import email as email_lib
    from app.tools.email_tool import _fetch_inbox

    raw = email_lib.message_from_string(
        "From: sender@example.com\r\nTo: me@example.com\r\nSubject: Hello\r\n"
        "Date: Mon, 1 Jan 2026 00:00:00 +0000\r\n\r\nBody text here."
    ).as_bytes()

    mock_conn = MagicMock()
    mock_conn.login.return_value = ("OK", [])
    mock_conn.select.return_value = ("OK", [])
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("OK", [(b"1", raw)])

    with patch("app.tools.email_tool._get_credentials", new=AsyncMock(return_value=creds)), \
         patch("app.tools.email_tool.imaplib.IMAP4_SSL", return_value=mock_conn):
        result = await _fetch_inbox(session, limit=10)

    assert len(result) == 1
    assert result[0]["from"] == "sender@example.com"
    assert result[0]["subject"] == "Hello"
    assert "Body text here" in result[0]["body"]
    mock_conn.login.assert_called_once_with("me@example.com", "secret")


@pytest.mark.asyncio
async def test_send_email_returns_error_when_no_integration_configured(session):
    from app.tools.email_tool import _send_email
    with patch("app.tools.email_tool._get_credentials", new=AsyncMock(return_value=None)):
        result = await _send_email(session, to=["x@y.com"], subject="s", body="b")
    assert "error" in result


@pytest.mark.asyncio
async def test_send_email_calls_smtp_login_and_sendmail(session, creds):
    from app.tools.email_tool import _send_email

    mock_server = MagicMock()

    with patch("app.tools.email_tool._get_credentials", new=AsyncMock(return_value=creds)), \
         patch("app.tools.email_tool.smtplib.SMTP", return_value=mock_server):
        result = await _send_email(session, to=["dest@example.com"], subject="Hi", body="Hello")

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("me@example.com", "secret")
    assert mock_server.sendmail.call_count == 1
    args = mock_server.sendmail.call_args[0]
    assert args[1] == ["dest@example.com"]
    assert "message_id" in result


@pytest.mark.asyncio
async def test_execute_send_wraps_smtp_failure_as_retryable_tool_error(session, creds):
    import smtplib
    from app.tools.email_tool import EmailTool

    tool = EmailTool()
    with patch("app.tools.email_tool._get_credentials", new=AsyncMock(return_value=creds)), \
         patch("app.tools.email_tool.smtplib.SMTP", side_effect=smtplib.SMTPConnectError(421, "down")):
        result = await tool.execute(
            {"action": "send", "to": ["x@y.com"], "subject": "s", "body": "b", "hitl_approved": True},
            session,
        )

    assert result.ok is False
    assert result.retryable is True
