from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError


class BrowserTool(BaseTool):
    name = "browser"
    description = (
        "Control a headless Chromium browser running inside the secure sandbox. "
        "Navigate URLs, click elements, fill forms, extract text, and take screenshots."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action":   {"type": "string",
                         "enum": ["navigate", "click", "fill", "extract_text",
                                  "screenshot", "find_links", "wait_for_selector", "scroll"]},
            "url":      {"type": "string"},
            "selector": {"type": "string"},
            "value":    {"type": "string"},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action")
        client = SandboxRpcClient(session.sandbox_endpoint, timeout_s=60.0)
        try:
            result = await client.call(f"browser.{action}", params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            retryable = e.code == -32000
            return ToolResult(ok=False, error=e.message, retryable=retryable)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
