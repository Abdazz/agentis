import uuid
import pytest
from sqlalchemy import select
from app.models.tool_config import RegisteredTool


@pytest.mark.asyncio
async def test_registered_tool_defaults(db_session):
    tool = RegisteredTool(name=f"browser-{uuid.uuid4().hex[:8]}", source="builtin")
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    assert tool.id is not None
    assert tool.enabled_globally is True
    assert tool.allowed_orgs is None  # None = all orgs
    assert tool.source == "builtin"
    assert tool.mcp_url is None
    assert tool.openapi_spec_url is None


@pytest.mark.asyncio
async def test_registered_tool_unique_name(db_session):
    from sqlalchemy.exc import IntegrityError
    unique_name = f"browser-{uuid.uuid4().hex[:8]}"
    db_session.add(RegisteredTool(name=unique_name, source="builtin"))
    await db_session.commit()
    db_session.add(RegisteredTool(name=unique_name, source="builtin"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
