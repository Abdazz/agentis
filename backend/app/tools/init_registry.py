from app.tools.registry import tool_registry
from app.tools.browser import BrowserTool
from app.tools.code_executor import CodeExecutorTool
from app.tools.file_system import FileSystemTool
from app.tools.web_search import WebSearchTool
from app.tools.doc_parser import DocParserTool
from app.tools.http_caller import HttpCallerTool
from app.tools.email_tool import EmailTool
from app.tools.calendar_tool import CalendarTool
from app.tools.dispatch_tool import DispatchTool
from app.tools.gather_tool import GatherTool

_BUILTIN_TOOLS = [
    BrowserTool,
    CodeExecutorTool,
    FileSystemTool,
    WebSearchTool,
    DocParserTool,
    HttpCallerTool,
    EmailTool,
    CalendarTool,
    DispatchTool,
    GatherTool,
]


def register_all_tools() -> None:
    """Register all built-in tools. Called once at app startup."""
    for cls in _BUILTIN_TOOLS:
        tool_registry.register(cls)


async def seed_tool_configs(db) -> None:
    """Ensure every builtin tool has a row in tool_configs (idempotent)."""
    from sqlalchemy import select
    from app.models.tool_config import RegisteredTool
    for cls in _BUILTIN_TOOLS:
        instance = cls()
        result = await db.execute(select(RegisteredTool).where(RegisteredTool.name == instance.name))
        if result.scalar_one_or_none() is None:
            db.add(RegisteredTool(name=instance.name, source="builtin"))
    await db.commit()
