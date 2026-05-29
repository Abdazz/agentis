from app.orchestrator.tools_adapter import build_tool_schemas, filter_tools
from app.tools.registry import ToolRegistry
from app.tools.web_search import WebSearchTool
from app.tools.file_system import FileSystemTool


def test_build_tool_schemas_produces_anthropic_format():
    reg = ToolRegistry()
    reg.register(WebSearchTool)
    schemas = build_tool_schemas(reg, allowed=None)
    assert len(schemas) == 1
    s = schemas[0]
    assert s["name"] == "web_search"
    assert "description" in s
    assert s["input_schema"]["type"] == "object"


def test_filter_tools_respects_allowlist():
    reg = ToolRegistry()
    reg.register(WebSearchTool)
    reg.register(FileSystemTool)
    schemas = build_tool_schemas(reg, allowed=["web_search"])
    names = [s["name"] for s in schemas]
    assert names == ["web_search"]


def test_filter_tools_none_allows_all():
    reg = ToolRegistry()
    reg.register(WebSearchTool)
    reg.register(FileSystemTool)
    assert len(filter_tools(reg, None)) == 2
