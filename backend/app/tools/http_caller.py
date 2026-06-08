from urllib.parse import urlparse
from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError
from app.config import settings


class HttpCallerTool(BaseTool):
    name = "http_caller"
    description = (
        "Make HTTP requests to external APIs from inside the secure sandbox. "
        "GET requests are always allowed. Non-GET requests to domains not on the safe list "
        "require human confirmation (HITL) before execution."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "method":  {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
            "url":     {"type": "string"},
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "body":    {"type": "string"},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["method", "url"],
    }

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def _needs_hitl(self, method: str, url: str) -> bool:
        if method.upper() == "GET":
            return False
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return True  # Non-HTTPS non-GET always requires HITL
        return parsed.netloc.lower() not in settings.http_caller_safe_domain_set

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        method = params.get("method", "GET").upper()
        url = params.get("url", "")

        if self._needs_hitl(method, url):
            return ToolResult(
                ok=False,
                error=f"HITL required: {method} {url} needs human confirmation before execution.",
                retryable=False,
                data={"hitl_required": True, "method": method, "url": url},
            )

        client = SandboxRpcClient(session.sandbox_endpoint, timeout_s=float(params.get("timeout", 30)) + 5)
        try:
            result = await client.call("http_caller.request", params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            return ToolResult(ok=False, error=e.message, retryable=e.code == -32000)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
