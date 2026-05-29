from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError


class FileSystemTool(BaseTool):
    name = "file_system"
    description = (
        "Read, write, list, delete, and compress files within the agent's /workspace. "
        "All paths are relative to /workspace and must not escape it."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["write", "read", "list", "delete", "copy", "compress"]},
            "path":   {"type": "string"},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        client = SandboxRpcClient(session.sandbox_endpoint)
        action = params.get("action")
        try:
            result = await client.call(f"file_system.{action}", params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            retryable = e.code == -32000
            return ToolResult(ok=False, error=e.message, retryable=retryable)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
