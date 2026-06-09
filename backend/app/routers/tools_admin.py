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


class RegisterMcpRequest(BaseModel):
    server_url: str


class RegisterOpenApiRequest(BaseModel):
    spec_url: str


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


@router.post("/mcp", status_code=status.HTTP_201_CREATED)
async def register_mcp_server(
    body: RegisterMcpRequest,
    _: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Auto-discover and register all tools exposed by an MCP server."""
    from app.services.mcp_discovery import discover_mcp_tools
    try:
        tools = await discover_mcp_tools(body.server_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP discovery failed: {e}",
        )

    from app.tools.registry import tool_registry
    registered: list[str] = []
    for tool in tools:
        # Register in the in-memory registry if not already present.
        if tool_registry.get(tool.name) is None:
            tool_registry._tools[tool.name] = tool

        # Persist to DB if not already recorded.
        result = await db.execute(
            select(RegisteredTool).where(RegisteredTool.name == tool.name)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            db.add(
                RegisteredTool(
                    name=tool.name,
                    source="mcp",
                    mcp_url=body.server_url,
                )
            )
            registered.append(tool.name)

    await db.commit()
    return {"registered": registered}


@router.post("/openapi", status_code=status.HTTP_201_CREATED)
async def register_openapi_spec(
    body: RegisterOpenApiRequest,
    _: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Fetch an OpenAPI spec and auto-register all discovered operations as tools."""
    from app.services.openapi_tool_gen import fetch_and_generate
    try:
        tools = await fetch_and_generate(body.spec_url)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"OpenAPI fetch failed: {e}")
    from app.tools.registry import tool_registry
    registered = []
    for tool in tools:
        if tool_registry.get(tool.name) is None:
            tool_registry._tools[tool.name] = tool
        result = await db.execute(select(RegisteredTool).where(RegisteredTool.name == tool.name))
        existing = result.scalar_one_or_none()
        if existing is None:
            db.add(RegisteredTool(name=tool.name, source="openapi",
                                  openapi_spec_url=body.spec_url))
            registered.append(tool.name)
    await db.commit()
    return {"registered": registered}
