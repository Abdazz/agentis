"""
Phase 1B smoke test: all 4 tools registered, schemas valid, web_search graceful without API key.
"""
import pytest
from app.tools.registry import ToolRegistry
from app.tools.browser import BrowserTool
from app.tools.code_executor import CodeExecutorTool
from app.tools.file_system import FileSystemTool
from app.tools.web_search import WebSearchTool
from app.tools.init_registry import register_all_tools
from app.tools.base import SessionContext


@pytest.fixture(autouse=True, scope="module")
def populated_registry():
    """Ensure registry is populated for tests in this module."""
    from app.tools.registry import tool_registry
    tool_registry._tools.clear()
    register_all_tools()
    yield
    tool_registry._tools.clear()


def test_all_four_tools_registered():
    from app.tools.registry import tool_registry
    names = set(tool_registry.list_names())
    assert {"browser", "code_executor", "file_system", "web_search"}.issubset(names)


def test_each_tool_has_name_description_schema():
    from app.tools.registry import tool_registry
    for tool in tool_registry.get_all():
        assert tool.name, f"{type(tool).__name__} missing name"
        assert tool.description, f"{type(tool).__name__} missing description"
        assert isinstance(tool.input_schema, dict), f"{type(tool).__name__} missing input_schema"
        assert tool.input_schema.get("type") == "object"


@pytest.mark.asyncio
async def test_web_search_no_key_returns_empty(monkeypatch):
    from app.tools.web_search import settings as ws_settings
    monkeypatch.setattr(ws_settings, "brave_api_key", "")
    monkeypatch.setattr(ws_settings, "search_backend", "brave")

    session = SessionContext(session_id="s", task_id="t", sandbox_endpoint="http://localhost")
    tool = WebSearchTool()
    result = await tool.execute({"query": "test"}, session)
    assert result.ok is True
    assert result.data["results"] == []


def test_tool_input_schemas_are_valid():
    from app.tools.registry import tool_registry
    for tool in tool_registry.get_all():
        schema = tool.input_schema
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_registry_get_returns_correct_type():
    from app.tools.registry import tool_registry
    assert isinstance(tool_registry.get("browser"), BrowserTool)
    assert isinstance(tool_registry.get("code_executor"), CodeExecutorTool)
    assert isinstance(tool_registry.get("file_system"), FileSystemTool)
    assert isinstance(tool_registry.get("web_search"), WebSearchTool)
