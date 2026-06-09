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

    async def is_enabled_for_org(self, name: str, org_id: str | None, db) -> bool:
        """Check DB for per-tool enabled state. Returns True if no record exists."""
        from sqlalchemy import select
        from app.models.tool_config import RegisteredTool
        result = await db.execute(select(RegisteredTool).where(RegisteredTool.name == name))
        record = result.scalar_one_or_none()
        if record is None:
            return True  # No DB record = tool is allowed
        if not record.enabled_globally:
            return False
        if record.allowed_orgs is not None and org_id not in record.allowed_orgs:
            return False
        return True


# Module-level registry populated at startup
tool_registry = ToolRegistry()
