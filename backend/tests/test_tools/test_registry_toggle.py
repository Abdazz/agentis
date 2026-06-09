import pytest
from unittest.mock import AsyncMock
from app.tools.registry import ToolRegistry
from app.tools.base import BaseTool, SessionContext, ToolResult


class FakeTool(BaseTool):
    name = "fake_tool"
    description = "test"
    input_schema = {}

    async def execute(self, params, session):
        return ToolResult(ok=True)


@pytest.mark.asyncio
async def test_is_enabled_for_org_no_db_record_defaults_true():
    registry = ToolRegistry()
    registry.register(FakeTool)
    # No DB record → defaults to enabled
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=lambda: None))
    assert await registry.is_enabled_for_org("fake_tool", org_id=None, db=mock_db) is True


@pytest.mark.asyncio
async def test_is_enabled_for_org_globally_disabled():
    from types import SimpleNamespace
    registry = ToolRegistry()
    registry.register(FakeTool)

    mock_db = AsyncMock()
    record = SimpleNamespace(name="fake_tool", enabled_globally=False, allowed_orgs=None)
    mock_db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=lambda: record))
    assert await registry.is_enabled_for_org("fake_tool", org_id=None, db=mock_db) is False


@pytest.mark.asyncio
async def test_is_enabled_for_org_restricted_to_specific_orgs():
    import uuid
    from types import SimpleNamespace
    registry = ToolRegistry()
    registry.register(FakeTool)

    org_id = str(uuid.uuid4())
    other_org_id = str(uuid.uuid4())
    record = SimpleNamespace(name="fake_tool", enabled_globally=True, allowed_orgs=[org_id])

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=lambda: record))
    assert await registry.is_enabled_for_org("fake_tool", org_id=org_id, db=mock_db) is True

    mock_db.execute = AsyncMock(return_value=AsyncMock(scalar_one_or_none=lambda: record))
    assert await registry.is_enabled_for_org("fake_tool", org_id=other_org_id, db=mock_db) is False
