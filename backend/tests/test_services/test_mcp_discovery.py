"""Tests for MCP tool auto-discovery (Phase 3A Task 4)."""
import types

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_discover_mcp_tools_returns_proxy_tools():
    """discover_mcp_tools wraps each raw tool definition into a McpProxyTool."""
    from app.services.mcp_discovery import discover_mcp_tools

    # Use SimpleNamespace to avoid MagicMock's special `name` handling.
    fake_tool = types.SimpleNamespace(
        name="get_weather",
        description="Get weather for a city",
        inputSchema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )

    with patch(
        "app.services.mcp_discovery._list_mcp_tools",
        new=AsyncMock(return_value=[fake_tool]),
    ):
        tools = await discover_mcp_tools("http://mcp-server:8080")

    assert len(tools) == 1
    tool = tools[0]
    assert tool.name == "mcp__get_weather"
    assert tool.description == "Get weather for a city"
    assert tool._mcp_url == "http://mcp-server:8080"


@pytest.mark.asyncio
async def test_discover_mcp_tools_handles_dict_response():
    """discover_mcp_tools also handles plain dict tool definitions (JSON responses)."""
    from app.services.mcp_discovery import discover_mcp_tools

    fake_tool = {
        "name": "search_web",
        "description": "Search the web",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
    }

    with patch(
        "app.services.mcp_discovery._list_mcp_tools",
        new=AsyncMock(return_value=[fake_tool]),
    ):
        tools = await discover_mcp_tools("http://mcp-server:8080")

    assert len(tools) == 1
    assert tools[0].name == "mcp__search_web"


@pytest.mark.asyncio
async def test_discover_mcp_tools_skips_nameless_entries():
    """Entries without a name are silently ignored."""
    from app.services.mcp_discovery import discover_mcp_tools

    fake_tools = [
        types.SimpleNamespace(name="valid_tool", description="ok", inputSchema={}),
        types.SimpleNamespace(name="", description="no name", inputSchema={}),
        {"description": "also no name"},
    ]

    with patch(
        "app.services.mcp_discovery._list_mcp_tools",
        new=AsyncMock(return_value=fake_tools),
    ):
        tools = await discover_mcp_tools("http://mcp-server:8080")

    assert len(tools) == 1
    assert tools[0].name == "mcp__valid_tool"


@pytest.mark.asyncio
async def test_mcp_proxy_tool_delegates_to_rpc():
    """McpProxyTool.execute() calls _call_mcp_tool and wraps the result."""
    from app.services.mcp_discovery import McpProxyTool
    from app.tools.base import SessionContext

    tool = McpProxyTool(
        tool_name="get_weather",
        mcp_server_url="http://mcp-server:8080",
        description="Get weather",
        input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
    )

    session = SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="")
    with patch(
        "app.services.mcp_discovery._call_mcp_tool",
        new=AsyncMock(return_value={"weather": "sunny"}),
    ):
        result = await tool.execute({"city": "Paris"}, session)

    assert result.ok is True
    assert result.data == {"weather": "sunny"}


@pytest.mark.asyncio
async def test_mcp_proxy_tool_returns_error_on_failure():
    """McpProxyTool.execute() returns a retryable ToolResult when RPC raises."""
    from app.services.mcp_discovery import McpProxyTool
    from app.tools.base import SessionContext

    tool = McpProxyTool(
        tool_name="failing_tool",
        mcp_server_url="http://mcp-server:8080",
        description="Fails",
        input_schema={},
    )

    session = SessionContext(session_id="s1", task_id="t1", sandbox_endpoint="")
    with patch(
        "app.services.mcp_discovery._call_mcp_tool",
        new=AsyncMock(side_effect=Exception("connection refused")),
    ):
        result = await tool.execute({}, session)

    assert result.ok is False
    assert "connection refused" in result.error
    assert result.retryable is True


@pytest.mark.asyncio
async def test_mcp_proxy_tool_name_prefixed():
    """McpProxyTool.name is always prefixed with 'mcp__'."""
    from app.services.mcp_discovery import McpProxyTool

    tool = McpProxyTool(
        tool_name="my_tool",
        mcp_server_url="http://server",
        description="desc",
        input_schema={},
    )
    assert tool.name == "mcp__my_tool"
    assert tool._mcp_name == "my_tool"
    assert tool._mcp_url == "http://server"
