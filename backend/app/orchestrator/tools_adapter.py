"""Bridge between the Agentis ToolRegistry and LangChain's bind_tools (ADR-1C-02)."""
from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry


def filter_tools(registry: ToolRegistry, allowed: list[str] | None) -> list[BaseTool]:
    tools = registry.get_all()
    if allowed is None:
        return tools
    allowset = set(allowed)
    return [t for t in tools if t.name in allowset]


def build_tool_schemas(registry: ToolRegistry, allowed: list[str] | None) -> list[dict]:
    """Anthropic-native tool schema list for ChatModel.bind_tools()."""
    schemas = []
    for tool in filter_tools(registry, allowed):
        schema = tool.input_schema or {"type": "object", "properties": {}}
        schemas.append({
            "name": tool.name,
            "description": tool.description,
            "input_schema": schema,
        })
    return schemas
