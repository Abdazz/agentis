from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from app.auth.dependencies import require_admin
from app.database import get_db
from app.models.tool_config import RegisteredTool
from app.models.user import User

router = APIRouter(prefix="/admin/tools", tags=["admin"])


class ToolConfigResponse(BaseModel):
    name: str
    enabled_globally: bool
    allowed_orgs: Optional[list] = None
    source: str
    mcp_url: Optional[str] = None
    openapi_spec_url: Optional[str] = None

    model_config = {"from_attributes": True}


class PatchToolRequest(BaseModel):
    enabled_globally: Optional[bool] = None
    allowed_orgs: Optional[list] = None


class MCPToolRequest(BaseModel):
    name: str
    mcp_url: str
    enabled_globally: bool = True


class OpenAPIToolRequest(BaseModel):
    name: str
    openapi_spec_url: str
    enabled_globally: bool = True


@router.get("", response_model=list[ToolConfigResponse])
async def list_tools(
    _: User = Depends(require_admin),
    db=Depends(get_db),
):
    result = await db.execute(select(RegisteredTool).order_by(RegisteredTool.name))
    return result.scalars().all()


@router.patch("/{tool_name}", response_model=ToolConfigResponse)
async def patch_tool(
    tool_name: str,
    body: PatchToolRequest,
    _: User = Depends(require_admin),
    db=Depends(get_db),
):
    result = await db.execute(select(RegisteredTool).where(RegisteredTool.name == tool_name))
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")
    if body.enabled_globally is not None:
        tool.enabled_globally = body.enabled_globally
    if body.allowed_orgs is not None:
        tool.allowed_orgs = body.allowed_orgs if body.allowed_orgs else None
    await db.commit()
    await db.refresh(tool)
    return tool


@router.post("/mcp", response_model=ToolConfigResponse, status_code=status.HTTP_201_CREATED)
async def register_mcp_tool(
    body: MCPToolRequest,
    _: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Register a new MCP (Model Context Protocol) tool by URL."""
    existing = await db.execute(select(RegisteredTool).where(RegisteredTool.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tool '{body.name}' already registered",
        )
    tool = RegisteredTool(
        name=body.name,
        source="mcp",
        mcp_url=body.mcp_url,
        enabled_globally=body.enabled_globally,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return tool


@router.post("/openapi", response_model=ToolConfigResponse, status_code=status.HTTP_201_CREATED)
async def register_openapi_tool(
    body: OpenAPIToolRequest,
    _: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Register a new tool from an OpenAPI spec URL (stub — full parsing in Phase 3A Task 5)."""
    existing = await db.execute(select(RegisteredTool).where(RegisteredTool.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tool '{body.name}' already registered",
        )
    tool = RegisteredTool(
        name=body.name,
        source="openapi",
        openapi_spec_url=body.openapi_spec_url,
        enabled_globally=body.enabled_globally,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    return tool
