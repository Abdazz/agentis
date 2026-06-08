import pytest
from unittest.mock import AsyncMock, patch
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="http://sandbox:9999")


@pytest.fixture
def tool():
    from app.tools.http_caller import HttpCallerTool
    return HttpCallerTool()


def test_http_caller_name(tool):
    assert tool.name == "http_caller"


@pytest.mark.asyncio
async def test_get_request_executes_directly(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.http_caller.settings.http_caller_safe_domains", "")
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"status": 200, "body": "OK", "headers": {}, "duration_ms": 50})
    with patch("app.tools.http_caller.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute(
            {"method": "GET", "url": "https://example.com/api/data"}, session
        )
    assert result.ok is True
    assert result.data["status"] == 200
    mock_client.call.assert_called_once()


@pytest.mark.asyncio
async def test_non_get_to_safe_domain_executes(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.http_caller.settings.http_caller_safe_domains", "api.github.com")
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"status": 201, "body": "{}", "headers": {}, "duration_ms": 80})
    with patch("app.tools.http_caller.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute(
            {"method": "POST", "url": "https://api.github.com/repos/x/y/issues", "body": "{}"}, session
        )
    assert result.ok is True
    mock_client.call.assert_called_once()


@pytest.mark.asyncio
async def test_non_get_to_unsafe_domain_requires_hitl(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.http_caller.settings.http_caller_safe_domains", "")
    result = await tool.execute(
        {"method": "POST", "url": "https://external.example.com/webhook", "body": "data"}, session
    )
    assert result.ok is False
    assert result.data.get("hitl_required") is True
    assert result.data.get("method") == "POST"
    assert result.data.get("url") == "https://external.example.com/webhook"


@pytest.mark.asyncio
async def test_rpc_error_returns_not_ok(tool, session, monkeypatch):
    monkeypatch.setattr("app.tools.http_caller.settings.http_caller_safe_domains", "")
    from app.sandbox.rpc_client import RpcError
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(side_effect=RpcError(code=-32001, message="Timeout"))
    with patch("app.tools.http_caller.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute(
            {"method": "GET", "url": "https://slow.example.com"}, session
        )
    assert result.ok is False
    assert "Timeout" in result.error
