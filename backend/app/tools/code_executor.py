from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError
from app.config import settings


class CodeExecutorTool(BaseTool):
    name = "code_executor"
    description = (
        "Execute Python 3.12, Node.js 22, or Bash code inside the secure sandbox. "
        "Generated files in /workspace/outputs/ are captured as artifacts."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action":    {"type": "string", "enum": ["run_python", "run_node", "run_bash"]},
            "code":      {"type": "string"},
            "command":   {"type": "string"},
            "timeout_s": {"type": "integer", "default": 120},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action")
        timeout = min(int(params.get("timeout_s", settings.code_executor_timeout_s)), 120)
        rpc_params = dict(params)
        rpc_params["timeout_s"] = timeout

        client = SandboxRpcClient(session.sandbox_endpoint, timeout_s=timeout + 15)
        try:
            result = await client.call(f"code_executor.{action}", rpc_params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            return ToolResult(ok=False, error=e.message, retryable=False)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
