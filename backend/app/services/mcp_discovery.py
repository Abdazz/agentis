"""MCP server tool auto-discovery (spec §6.5, Phase 3A)."""
import httpx
from app.config import settings
from app.tools.base import BaseTool, SessionContext, ToolResult


async def _list_mcp_tools(server_url: str) -> list:
    """Call MCP server tools/list endpoint and return raw tool definitions."""
    async with httpx.AsyncClient(timeout=settings.mcp_timeout_s) as client:
        resp = await client.post(
            f"{server_url.rstrip('/')}/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", {}).get("tools", [])


async def _call_mcp_tool(server_url: str, tool_name: str, params: dict) -> dict:
    """Invoke an MCP tool via JSON-RPC."""
    async with httpx.AsyncClient(timeout=settings.mcp_timeout_s) as client:
        resp = await client.post(
            f"{server_url.rstrip('/')}/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": params},
            },
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", "MCP error"))
        result = data.get("result", {})
        if isinstance(result, dict) and "content" in result:
            return {"content": result["content"]}
        return result if isinstance(result, dict) else {"output": result}


class McpProxyTool(BaseTool):
    """Dynamic BaseTool that proxies calls to an MCP server.

    BaseTool.__init_subclass__ only validates concrete (non-abstract) subclasses,
    checking that *class-level* name/description are non-empty.  We satisfy it with
    non-empty class-level sentinel values and then override per-instance in __init__.
    """

    # Class-level sentinels that satisfy BaseTool.__init_subclass__ validation.
    name: str = "mcp__proxy"
    description: str = "Dynamic MCP proxy tool"
    input_schema: dict = {}

    def __init__(
        self,
        tool_name: str,
        mcp_server_url: str,
        description: str,
        input_schema: dict,
    ) -> None:
        # Override at instance level — these shadow the class-level attributes.
        self.name = f"mcp__{tool_name}"
        self.description = description
        self.input_schema = input_schema
        self._mcp_name = tool_name
        self._mcp_url = mcp_server_url

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        try:
            data = await _call_mcp_tool(self._mcp_url, self._mcp_name, params)
            return ToolResult(ok=True, data=data)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)


async def discover_mcp_tools(server_url: str) -> list[McpProxyTool]:
    """Discover all tools from an MCP server and return McpProxyTool instances."""
    raw_tools = await _list_mcp_tools(server_url)
    tools: list[McpProxyTool] = []
    for t in raw_tools:
        # Support both object-style (MCP SDK types) and dict-style responses.
        if hasattr(t, "name"):
            name = t.name
            desc = getattr(t, "description", "") or ""
            schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", None) or {}
        else:
            name = t.get("name", "")
            desc = t.get("description", "") or ""
            schema = t.get("inputSchema", t.get("input_schema", {})) or {}

        if name:
            tools.append(
                McpProxyTool(
                    tool_name=name,
                    mcp_server_url=server_url,
                    description=desc,
                    input_schema=schema,
                )
            )
    return tools
