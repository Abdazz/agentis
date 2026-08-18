import pytest
import uuid as _uuid
from httpx import AsyncClient
from unittest.mock import patch


async def _make_user_and_token(client: AsyncClient) -> str:
    email = f"user_{_uuid.uuid4().hex[:6]}@test.com"
    resp = await client.post("/api/v1/auth/register",
                             json={"email": email, "password": "Pass1234!Secret"})
    assert resp.status_code == 201
    login = await client.post("/api/v1/auth/login",
                              json={"email": email, "password": "Pass1234!Secret"})
    return login.json()["access_token"]


async def _make_admin_and_token(client: AsyncClient, db_session) -> str:
    """Installing a plugin registers new tools into the org's tool registry —
    a privileged action, same as MCP/OpenAPI registration in tools_admin.py —
    so it requires admin/operator (require_admin), not a plain user."""
    from app.models.user import User, UserRole
    from app.auth.password import hash_password
    from datetime import datetime, timezone

    email = f"admin_{_uuid.uuid4().hex[:6]}@test.com"
    user = User(
        id=_uuid.uuid4(),
        email=email,
        password_hash=hash_password("Pass1234!Secret"),
        role=UserRole.admin,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    await db_session.commit()
    login = await client.post("/api/v1/auth/login",
                              json={"email": email, "password": "Pass1234!Secret"})
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_list_plugins_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/marketplace/plugins")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_plugins_returns_results(client: AsyncClient):
    token = await _make_user_and_token(client)
    resp = await client.get(
        "/api/v1/marketplace/plugins",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_plugins_filter_installed(client: AsyncClient):
    token = await _make_user_and_token(client)
    resp = await client.get(
        "/api/v1/marketplace/plugins?installed=false",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert all(not p["installed"] for p in data)


@pytest.mark.asyncio
async def test_install_mcp_plugin_marks_as_installed(client: AsyncClient, db_session):
    from app.models.marketplace import MarketplacePlugin

    token = await _make_admin_and_token(client, db_session)
    plugin = MarketplacePlugin(
        name="Test MCP Plugin", slug=f"test-mcp-{_uuid.uuid4().hex[:6]}",
        source_type="mcp", url="http://example.com/mcp",
    )
    db_session.add(plugin)
    await db_session.commit()

    fake_tool = type("T", (), {"name": "test_mcp_tool", "__class__": type})()
    with patch("app.routers.marketplace.discover_mcp_tools", return_value=[fake_tool]):
        resp = await client.post(
            f"/api/v1/marketplace/plugins/{plugin.slug}/install",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["installed"] is True
    assert data["registered_tool_name"] == "test_mcp_tool"


@pytest.mark.asyncio
async def test_install_requires_admin(client: AsyncClient):
    """Regular users cannot register arbitrary MCP/OpenAPI sources as tools —
    same RBAC tier as tools_admin.py's MCP/OpenAPI registration endpoints."""
    token = await _make_user_and_token(client)
    resp = await client.post(
        "/api/v1/marketplace/plugins/some-slug/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_install_unknown_plugin_returns_404(client: AsyncClient, db_session):
    token = await _make_admin_and_token(client, db_session)
    resp = await client.post(
        "/api/v1/marketplace/plugins/nonexistent-slug-xyz/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_install_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/marketplace/plugins/weather-mcp/install")
    assert resp.status_code == 401
