"""Marketplace endpoints: browse and install community plugins (Phase 4C)."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.marketplace import MarketplacePlugin
from app.models.user import User
from app.services.mcp_discovery import discover_mcp_tools
from app.services.openapi_tool_gen import fetch_and_generate
from app.tools.registry import tool_registry
from app.models.tool_config import RegisteredTool

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
) -> list[PluginResponse]:
    stmt = select(MarketplacePlugin).order_by(MarketplacePlugin.name)
    if installed is not None:
        stmt = stmt.where(MarketplacePlugin.installed == installed)
    result = await db.execute(stmt)
    return list(result.scalars().all())


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
        tool_registry.register(tool.__class__)
        existing = await db.execute(
            select(RegisteredTool).where(RegisteredTool.name == tool.name)
        )
        if existing.scalar_one_or_none() is None:
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
