from app.tools.base import BaseTool, SessionContext, ToolResult
from app.sandbox.rpc_client import SandboxRpcClient, RpcError


class DocParserTool(BaseTool):
    name = "doc_parser"
    description = (
        "Parse documents (PDF, DOCX, XLSX, HTML, Markdown) running inside the secure sandbox. "
        "Extract text content, tables, and metadata. Convert between formats."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["parse", "extract_tables", "convert"],
                "description": "parse → full text+metadata; extract_tables → structured tables; convert → new format file",
            },
            "file_path": {"type": "string", "description": "Absolute path inside /workspace"},
            "target_format": {
                "type": "string",
                "enum": ["markdown", "txt", "json", "csv"],
                "description": "Required for 'convert' action",
            },
        },
        "required": ["action", "file_path"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action", "parse")
        client = SandboxRpcClient(session.sandbox_endpoint, timeout_s=120.0)
        method = f"doc_parser.{action}"
        try:
            result = await client.call(method, params)
            return ToolResult(ok=True, data=result)
        except RpcError as e:
            return ToolResult(ok=False, error=e.message, retryable=e.code == -32000)
        except Exception as e:
            return ToolResult(ok=False, error=str(e), retryable=True)
