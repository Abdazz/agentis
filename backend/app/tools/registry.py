from app.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool_class: type[BaseTool]) -> None:
        tool = tool_class()
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_all(self) -> list[BaseTool]:
        return list(self._tools.values())


# Module-level registry populated at startup
tool_registry = ToolRegistry()
