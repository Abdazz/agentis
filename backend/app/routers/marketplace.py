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
) -> list[PluginResponse]:
    stmt = select(MarketplacePlugin).order_by(MarketplacePlugin.name)
    if installed is not None:
        stmt = stmt.where(MarketplacePlugin.installed == installed)
    result = await db.execute(stmt)
    return list(result.scalars().all())
