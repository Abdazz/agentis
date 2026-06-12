# Phase 4C — Agent Marketplace (Community Tool Plugins)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a curated community marketplace of tool plugins. Users/admins browse available plugins, install one-click, and the tool becomes available in the tool registry via the existing MCP/OpenAPI proxy infrastructure from Phase 3A.

**Architecture:** A `MarketplacePlugin` model stores community-contributed plugin definitions (name, description, source_type `mcp|openapi`, url, version). `GET /marketplace/plugins` lists available (uninstalled) plugins. `POST /marketplace/plugins/{id}/install` delegates to the existing `discover_mcp_tools`/`fetch_and_generate` services from `tools_admin.py`, then marks the plugin as installed. A seed file ships a handful of example plugins for discovery.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, pytest-asyncio

---

### Task 1: `MarketplacePlugin` model + migration + seed data

**Files:**
- Create: `backend/app/models/marketplace.py`
- Create: `backend/alembic/versions/a4b5c6d7e8f9_add_marketplace_plugins.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_models/test_marketplace.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models/test_marketplace.py
import pytest, uuid
from datetime import datetime, timezone
from app.models.marketplace import MarketplacePlugin


@pytest.mark.asyncio
async def test_create_marketplace_plugin(db_session):
    plugin = MarketplacePlugin(
        id=uuid.uuid4(),
        name="weather",
        slug="weather-mcp",
        description="Live weather data via Open-Meteo",
        source_type="mcp",
        url="https://weather.example.com/mcp",
        version="1.0.0",
        author="community",
    )
    db_session.add(plugin)
    await db_session.commit()
    await db_session.refresh(plugin)
    assert plugin.name == "weather"
    assert plugin.installed is False
    assert plugin.source_type == "mcp"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_models/test_marketplace.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement MarketplacePlugin model**

```python
# backend/app/models/marketplace.py
"""Community marketplace plugin registry (Phase 4C)."""
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class MarketplacePlugin(TimestampMixin, Base):
    __tablename__ = "marketplace_plugins"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)  # mcp | openapi
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    author: Mapped[str] = mapped_column(String(100), nullable=False, default="community")
    installed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    registered_tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
```

- [ ] **Step 4: Create migration**

```python
# backend/alembic/versions/a4b5c6d7e8f9_add_marketplace_plugins.py
"""add marketplace_plugins table

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_plugins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("version", sa.String(50), nullable=False, server_default="1.0.0"),
        sa.Column("author", sa.String(100), nullable=False, server_default="community"),
        sa.Column("installed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("registered_tool_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_marketplace_plugins_slug"),
    )
    op.create_index("ix_marketplace_plugins_slug", "marketplace_plugins", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_marketplace_plugins_slug", table_name="marketplace_plugins")
    op.drop_table("marketplace_plugins")
```

- [ ] **Step 5: Update models/__init__.py**

Add to `backend/app/models/__init__.py`:

```python
from app.models.marketplace import MarketplacePlugin
```

And add `"MarketplacePlugin"` to `__all__`.

- [ ] **Step 6: Run test**

```bash
cd backend && python3 -m pytest tests/test_models/test_marketplace.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/marketplace.py backend/alembic/versions/a4b5c6d7e8f9_add_marketplace_plugins.py backend/app/models/__init__.py backend/tests/test_models/test_marketplace.py
git commit -m "feat(4c): MarketplacePlugin model + marketplace_plugins migration"
```

---

### Task 2: Marketplace seed + `GET /marketplace/plugins` endpoint

**Files:**
- Create: `backend/app/services/marketplace_seed.py`
- Create: `backend/app/routers/marketplace.py`
- Modify: `backend/app/main.py` (register router + seed in lifespan)
- Test: `backend/tests/test_routers/test_marketplace.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_routers/test_marketplace.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_plugins_returns_seeded_plugins(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.get("/api/v1/marketplace/plugins", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # At least the seeded plugins are present
    assert len(data) >= 1
    plugin = data[0]
    assert "name" in plugin
    assert "slug" in plugin
    assert "source_type" in plugin
    assert "installed" in plugin


@pytest.mark.asyncio
async def test_list_plugins_requires_auth(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/marketplace/plugins")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_plugins_filter_installed(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.get("/api/v1/marketplace/plugins?installed=false", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(not p["installed"] for p in data)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python3 -m pytest tests/test_routers/test_marketplace.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement marketplace seed**

```python
# backend/app/services/marketplace_seed.py
"""Seed the marketplace_plugins table with curated community plugins."""
COMMUNITY_PLUGINS = [
    {
        "name": "Weather MCP",
        "slug": "weather-mcp",
        "description": "Live weather data via Open-Meteo (free, no API key)",
        "source_type": "mcp",
        "url": "https://mcp.weather.example.com/sse",
        "version": "1.0.0",
        "author": "community",
    },
    {
        "name": "GitHub OpenAPI",
        "slug": "github-openapi",
        "description": "GitHub REST API v3 — search repos, issues, PRs",
        "source_type": "openapi",
        "url": "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json",
        "version": "1.0.0",
        "author": "community",
    },
    {
        "name": "Wikipedia MCP",
        "slug": "wikipedia-mcp",
        "description": "Search and fetch Wikipedia articles as structured data",
        "source_type": "mcp",
        "url": "https://mcp.wikipedia.example.com/sse",
        "version": "1.0.0",
        "author": "community",
    },
]


async def seed_marketplace_plugins(db) -> None:
    from sqlalchemy import select
    from app.models.marketplace import MarketplacePlugin
    for p in COMMUNITY_PLUGINS:
        result = await db.execute(
            select(MarketplacePlugin).where(MarketplacePlugin.slug == p["slug"])
        )
        if result.scalar_one_or_none() is None:
            db.add(MarketplacePlugin(**p))
    await db.commit()
```

- [ ] **Step 4: Implement marketplace router**

```python
# backend/app/routers/marketplace.py
"""Marketplace endpoints: browse and install community plugins (Phase 4C)."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.marketplace import MarketplacePlugin
from app.models.user import User

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


class PluginResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    source_type: str
    url: str
    version: str
    author: str
    installed: bool
    registered_tool_name: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("/plugins", response_model=list[PluginResponse])
async def list_plugins(
    installed: Optional[bool] = Query(None, description="Filter by installed status"),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MarketplacePlugin]:
    stmt = select(MarketplacePlugin).order_by(MarketplacePlugin.name)
    if installed is not None:
        stmt = stmt.where(MarketplacePlugin.installed == installed)
    result = await db.execute(stmt)
    return list(result.scalars().all())
```

- [ ] **Step 5: Register router + seed in main.py**

In `backend/app/main.py`:

```python
from app.routers.marketplace import router as marketplace_router
from app.services.marketplace_seed import seed_marketplace_plugins
```

In the lifespan function, add inside the `async with AsyncSessionLocal() as db:` block:
```python
        await seed_marketplace_plugins(db)
```

And register:
```python
app.include_router(marketplace_router, prefix="/api/v1")
```

- [ ] **Step 6: Run tests**

```bash
cd backend && python3 -m pytest tests/test_routers/test_marketplace.py -v
```
Expected: PASS

- [ ] **Step 7: Run full suite**

```bash
cd backend && python3 -m pytest tests/ -x --tb=short -q 2>&1 | tail -5
```
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/marketplace_seed.py backend/app/routers/marketplace.py backend/app/main.py backend/tests/test_routers/test_marketplace.py
git commit -m "feat(4c): marketplace GET /plugins + seed 3 community plugins"
```

---

### Task 3: `POST /marketplace/plugins/{slug}/install` — one-click tool install

**Files:**
- Modify: `backend/app/routers/marketplace.py`
- Test: add to `backend/tests/test_routers/test_marketplace.py`

Installing a plugin calls the existing discovery service (`discover_mcp_tools` or `fetch_and_generate`) and marks the plugin as installed.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_routers/test_marketplace.py`:

```python
import uuid as _uuid
from unittest.mock import patch
from app.models.marketplace import MarketplacePlugin


@pytest.mark.asyncio
async def test_install_mcp_plugin_marks_as_installed(async_client: AsyncClient, auth_headers: dict, db_session):
    from app.models.marketplace import MarketplacePlugin
    plugin = MarketplacePlugin(
        id=_uuid.uuid4(),
        name="Test MCP", slug=f"test-mcp-{_uuid.uuid4().hex[:6]}",
        description="test", source_type="mcp",
        url="https://test-mcp.example.com/sse",
        version="1.0.0", author="test",
    )
    db_session.add(plugin)
    await db_session.commit()

    fake_tool = type("T", (), {"name": "test_mcp_tool"})()
    with patch("app.routers.marketplace.discover_mcp_tools", return_value=[fake_tool]):
        resp = await async_client.post(
            f"/api/v1/marketplace/plugins/{plugin.slug}/install",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["installed"] is True

    await db_session.refresh(plugin)
    assert plugin.installed is True


@pytest.mark.asyncio
async def test_install_unknown_plugin_returns_404(async_client: AsyncClient, auth_headers: dict):
    resp = await async_client.post(
        "/api/v1/marketplace/plugins/nonexistent-slug/install",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_install_already_installed_returns_409(async_client: AsyncClient, auth_headers: dict, db_session):
    plugin = MarketplacePlugin(
        id=_uuid.uuid4(),
        name="Already Installed", slug=f"already-{_uuid.uuid4().hex[:6]}",
        description="test", source_type="mcp",
        url="https://already.example.com/sse",
        version="1.0.0", author="test",
        installed=True,
    )
    db_session.add(plugin)
    await db_session.commit()
    resp = await async_client.post(
        f"/api/v1/marketplace/plugins/{plugin.slug}/install",
        headers=auth_headers,
    )
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python3 -m pytest tests/test_routers/test_marketplace.py::test_install_mcp_plugin_marks_as_installed tests/test_routers/test_marketplace.py::test_install_unknown_plugin_returns_404 tests/test_routers/test_marketplace.py::test_install_already_installed_returns_409 -v
```
Expected: FAIL

- [ ] **Step 3: Add install endpoint to marketplace router**

Add to `backend/app/routers/marketplace.py`:

```python
from fastapi import HTTPException
from app.auth.dependencies import require_admin
from app.services.mcp_discovery import discover_mcp_tools
from app.services.openapi_tool_gen import fetch_and_generate
from app.tools.registry import tool_registry
from app.models.tool_config import RegisteredTool


@router.post("/plugins/{slug}/install", response_model=PluginResponse)
async def install_plugin(
    slug: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarketplacePlugin:
    result = await db.execute(select(MarketplacePlugin).where(MarketplacePlugin.slug == slug))
    plugin = result.scalar_one_or_none()
    if plugin is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    if plugin.installed:
        raise HTTPException(status_code=409, detail="Plugin already installed")

    # Discover tools via the existing infrastructure
    if plugin.source_type == "mcp":
        tools = await discover_mcp_tools(plugin.url)
    else:
        tools = await fetch_and_generate(plugin.url)

    for tool in tools:
        tool_registry.register(tool)
        result2 = await db.execute(
            select(RegisteredTool).where(RegisteredTool.name == tool.name)
        )
        if result2.scalar_one_or_none() is None:
            db.add(RegisteredTool(
                name=tool.name,
                source=plugin.source_type,
                mcp_url=plugin.url if plugin.source_type == "mcp" else None,
                openapi_spec_url=plugin.url if plugin.source_type == "openapi" else None,
            ))

    plugin.installed = True
    if tools:
        plugin.registered_tool_name = tools[0].name
    await db.commit()
    await db.refresh(plugin)
    return plugin
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python3 -m pytest tests/test_routers/test_marketplace.py -v
```
Expected: all PASS

- [ ] **Step 5: Run full suite**

```bash
cd backend && python3 -m pytest tests/ -x --tb=short -q 2>&1 | tail -5
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/marketplace.py backend/tests/test_routers/test_marketplace.py
git commit -m "feat(4c): POST /marketplace/plugins/{slug}/install — one-click plugin install"
```
