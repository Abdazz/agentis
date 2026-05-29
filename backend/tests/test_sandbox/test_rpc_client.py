import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.sandbox.rpc_client import SandboxRpcClient, RpcError


@pytest.mark.asyncio
async def test_rpc_call_success():
    client = SandboxRpcClient("http://localhost:19999")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "jsonrpc": "2.0", "result": {"stdout": "hello\n"}, "id": 1
    })

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_http

        result = await client.call("code_executor.run_python", {"code": "print('hello')"})

    assert result == {"stdout": "hello\n"}


@pytest.mark.asyncio
async def test_rpc_error_response_raises():
    client = SandboxRpcClient("http://localhost:19999")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "jsonrpc": "2.0",
        "error": {"code": -32600, "message": "Unknown tool: missing"},
        "id": 1,
    })

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_http

        with pytest.raises(RpcError) as exc_info:
            await client.call("missing.action", {})

    assert exc_info.value.code == -32600
    assert "Unknown tool" in exc_info.value.message


@pytest.mark.asyncio
async def test_rpc_id_increments():
    client = SandboxRpcClient("http://localhost:19999")
    calls_made = []

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"jsonrpc": "2.0", "result": {}, "id": 1})

    async def capture_post(url, json=None, **kwargs):
        calls_made.append(json)
        return mock_response

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_http.post = capture_post
        mock_cls.return_value = mock_http

        await client.call("file_system.list", {"directory": "/"})
        await client.call("file_system.list", {"directory": "/"})

    assert calls_made[0]["id"] == 1
    assert calls_made[1]["id"] == 2
