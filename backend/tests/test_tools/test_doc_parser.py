import pytest
from unittest.mock import AsyncMock, patch
from app.tools.base import SessionContext


@pytest.fixture
def session():
    return SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="http://sandbox:9999")


@pytest.fixture
def tool():
    from app.tools.doc_parser import DocParserTool
    return DocParserTool()


def test_doc_parser_name(tool):
    assert tool.name == "doc_parser"


@pytest.mark.asyncio
async def test_parse_calls_sandbox_rpc(tool, session):
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"text": "Hello world", "metadata": {}, "truncated": False})
    with patch("app.tools.doc_parser.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute({"action": "parse", "file_path": "/workspace/doc.pdf"}, session)
    assert result.ok is True
    assert result.data["text"] == "Hello world"
    mock_client.call.assert_called_once_with("doc_parser.parse", {"action": "parse", "file_path": "/workspace/doc.pdf"})


@pytest.mark.asyncio
async def test_extract_tables_calls_sandbox_rpc(tool, session):
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(return_value={"tables": []})
    with patch("app.tools.doc_parser.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute({"action": "extract_tables", "file_path": "/workspace/data.xlsx"}, session)
    assert result.ok is True
    mock_client.call.assert_called_once_with("doc_parser.extract_tables", {"action": "extract_tables", "file_path": "/workspace/data.xlsx"})


@pytest.mark.asyncio
async def test_rpc_error_returns_not_ok(tool, session):
    from app.sandbox.rpc_client import RpcError
    mock_client = AsyncMock()
    mock_client.call = AsyncMock(side_effect=RpcError(code=-32000, message="File not found"))
    with patch("app.tools.doc_parser.SandboxRpcClient", return_value=mock_client):
        result = await tool.execute({"action": "parse", "file_path": "/workspace/missing.pdf"}, session)
    assert result.ok is False
    assert "File not found" in result.error
