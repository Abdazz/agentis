import types
import pytest
import uuid
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


async def _make_operator(db_session) -> "User":
    from app.models.user import User, UserRole
    from app.auth.password import hash_password
    from datetime import datetime, timezone
    user = User(
        id=uuid.uuid4(),
        email=f"op_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        role=UserRole.operator,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client: AsyncClient, email: str) -> str:
    resp = await client.post("/api/v1/auth/login",
                             json={"email": email, "password": "Pass1234!Secret"})
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_list_tools_requires_auth(client):
    resp = await client.get("/api/v1/admin/tools")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_tools_as_operator(client, db_session):
    from app.models.tool_config import RegisteredTool
    # Seed a tool record
    db_session.add(RegisteredTool(name=f"browser_{uuid.uuid4().hex[:6]}", source="builtin"))
    await db_session.commit()

    op = await _make_operator(db_session)
    token = await _login(client, op.email)
    resp = await client.get("/api/v1/admin/tools",
                            headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_patch_tool_disable(client, db_session):
    from app.models.tool_config import RegisteredTool
    tool_name = f"web_search_{uuid.uuid4().hex[:6]}"
    db_session.add(RegisteredTool(name=tool_name, source="builtin"))
    await db_session.commit()

    op = await _make_operator(db_session)
    token = await _login(client, op.email)
    resp = await client.patch(
        f"/api/v1/admin/tools/{tool_name}",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_globally": False},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled_globally"] is False


@pytest.mark.asyncio
async def test_patch_tool_nonexistent_returns_404(client, db_session):
    op = await _make_operator(db_session)
    token = await _login(client, op.email)
    resp = await client.patch(
        "/api/v1/admin/tools/nonexistent_tool_xyz",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_globally": False},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_tool_requires_auth(client):
    resp = await client.patch(
        "/api/v1/admin/tools/some_tool",
        json={"enabled_globally": False},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_register_mcp_server_discovers_and_registers_tools(client, db_session):
    """POST /admin/tools/mcp calls discover_mcp_tools and persists new tools."""
    from app.services.mcp_discovery import McpProxyTool

    tool_name = f"mcp_tool_{uuid.uuid4().hex[:6]}"
    fake_tool = McpProxyTool(
        tool_name=tool_name,
        mcp_server_url="http://mcp.example.com",
        description="A discovered tool",
        input_schema={"type": "object"},
    )

    op = await _make_operator(db_session)
    token = await _login(client, op.email)

    with patch(
        "app.services.mcp_discovery.discover_mcp_tools",
        new=AsyncMock(return_value=[fake_tool]),
    ):
        resp = await client.post(
            "/api/v1/admin/tools/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={"server_url": "http://mcp.example.com"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert f"mcp__{tool_name}" in data["registered"]


@pytest.mark.asyncio
async def test_register_mcp_server_skips_already_registered_tools(client, db_session):
    """Tools already in the DB are not re-added; they appear absent from 'registered'."""
    from app.models.tool_config import RegisteredTool
    from app.services.mcp_discovery import McpProxyTool

    tool_name = f"mcp_dup_{uuid.uuid4().hex[:6]}"
    # Pre-seed the DB record so the tool already exists.
    db_session.add(
        RegisteredTool(name=f"mcp__{tool_name}", source="mcp", mcp_url="http://mcp.example.com")
    )
    await db_session.commit()

    fake_tool = McpProxyTool(
        tool_name=tool_name,
        mcp_server_url="http://mcp.example.com",
        description="Already registered",
        input_schema={},
    )

    op = await _make_operator(db_session)
    token = await _login(client, op.email)

    with patch(
        "app.services.mcp_discovery.discover_mcp_tools",
        new=AsyncMock(return_value=[fake_tool]),
    ):
        resp = await client.post(
            "/api/v1/admin/tools/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={"server_url": "http://mcp.example.com"},
        )

    assert resp.status_code == 201
    data = resp.json()
    # Tool was already present — should NOT appear in registered list again.
    assert f"mcp__{tool_name}" not in data["registered"]


@pytest.mark.asyncio
async def test_register_mcp_server_returns_502_on_discovery_failure(client, db_session):
    """Returns 502 when discover_mcp_tools raises (unreachable MCP server)."""
    op = await _make_operator(db_session)
    token = await _login(client, op.email)

    with patch(
        "app.services.mcp_discovery.discover_mcp_tools",
        new=AsyncMock(side_effect=Exception("connection refused")),
    ):
        resp = await client.post(
            "/api/v1/admin/tools/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={"server_url": "http://unreachable-server"},
        )

    assert resp.status_code == 502
    body = resp.json()
    # Custom exception handler wraps errors as {"error": {"code": ..., "message": ...}}
    assert "MCP discovery failed" in body["error"]["message"]


@pytest.mark.asyncio
async def test_register_openapi_tool(client, db_session):
    op = await _make_operator(db_session)
    token = await _login(client, op.email)
    tool_name = f"openapi_tool_{uuid.uuid4().hex[:6]}"
    resp = await client.post(
        "/api/v1/admin/tools/openapi",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": tool_name, "openapi_spec_url": "http://api.example.com/openapi.json"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == tool_name
    assert data["source"] == "openapi"
    assert data["openapi_spec_url"] == "http://api.example.com/openapi.json"


@pytest.mark.asyncio
async def test_patch_tool_enable(client, db_session):
    from app.models.tool_config import RegisteredTool
    tool_name = f"disabled_tool_{uuid.uuid4().hex[:6]}"
    tool = RegisteredTool(name=tool_name, source="builtin", enabled_globally=False)
    db_session.add(tool)
    await db_session.commit()

    op = await _make_operator(db_session)
    token = await _login(client, op.email)
    resp = await client.patch(
        f"/api/v1/admin/tools/{tool_name}",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled_globally": True},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled_globally"] is True
