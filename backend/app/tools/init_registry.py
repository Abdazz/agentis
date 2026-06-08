from app.tools.registry import tool_registry
from app.tools.browser import BrowserTool
from app.tools.code_executor import CodeExecutorTool
from app.tools.file_system import FileSystemTool
from app.tools.web_search import WebSearchTool
from app.tools.doc_parser import DocParserTool
from app.tools.http_caller import HttpCallerTool


def register_all_tools() -> None:
    """Register all built-in tools. Called once at app startup."""
    tool_registry.register(BrowserTool)
    tool_registry.register(CodeExecutorTool)
    tool_registry.register(FileSystemTool)
    tool_registry.register(WebSearchTool)
    tool_registry.register(DocParserTool)
    tool_registry.register(HttpCallerTool)
