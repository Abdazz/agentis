import pytest
from app.tools.registry import ToolRegistry
from app.tools.base import BaseTool, SessionContext, ToolResult


class EchoTool(BaseTool):
    name = "echo"
    description = "Echoes params back."

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        return ToolResult(ok=True, data=params)


def test_registry_register_and_get():
    registry = ToolRegistry()
    registry.register(EchoTool)
    tool = registry.get("echo")
    assert isinstance(tool, EchoTool)


def test_registry_get_unknown_returns_none():
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_registry_list_names():
    registry = ToolRegistry()
    registry.register(EchoTool)
    assert "echo" in registry.list_names()


def test_registry_duplicate_raises():
    registry = ToolRegistry()
    registry.register(EchoTool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoTool)
