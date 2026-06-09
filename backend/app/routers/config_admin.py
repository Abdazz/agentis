import json
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.auth.dependencies import require_operator
from app.config import settings
from app.database import get_db
from app.models.system_config import SystemConfig
from app.models.user import User

router = APIRouter(prefix="/admin/config", tags=["admin"])

_CONFIG_KEY = "llm_config"


def _mask_api_key(key: str) -> str:
    """Return the first 4 chars followed by '***', or empty string if blank."""
    if not key:
        return ""
    return key[:4] + "***"


class LlmConfigResponse(BaseModel):
    provider: str
    model: str
    api_key_masked: str
    base_url: str


class LlmConfigPatch(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@router.get("/llm", response_model=LlmConfigResponse)
async def get_llm_config(
    _: User = Depends(require_operator),
    db=Depends(get_db),
):
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key == _CONFIG_KEY)
    )
    row = result.scalar_one_or_none()

    if row is not None:
        cfg = json.loads(row.value)
    else:
        cfg = {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
        }

    return LlmConfigResponse(
        provider=cfg.get("provider", settings.llm_provider),
        model=cfg.get("model", settings.llm_model),
        api_key_masked=_mask_api_key(cfg.get("api_key", settings.llm_api_key)),
        base_url=cfg.get("base_url", settings.llm_base_url),
    )


@router.patch("/llm", response_model=LlmConfigResponse)
async def patch_llm_config(
    body: LlmConfigPatch,
    _: User = Depends(require_operator),
    db=Depends(get_db),
):
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key == _CONFIG_KEY)
    )
    row = result.scalar_one_or_none()

    if row is not None:
        cfg = json.loads(row.value)
    else:
        # Seed from env defaults so partial patches work correctly
        cfg = {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
        }

    if body.provider is not None:
        cfg["provider"] = body.provider
    if body.model is not None:
        cfg["model"] = body.model
    if body.api_key is not None:
        cfg["api_key"] = body.api_key
    if body.base_url is not None:
        cfg["base_url"] = body.base_url

    serialized = json.dumps(cfg)
    # Use PostgreSQL upsert to handle both insert and update safely
    stmt = (
        pg_insert(SystemConfig)
        .values(key=_CONFIG_KEY, value=serialized)
        .on_conflict_do_update(index_elements=["key"], set_={"value": serialized})
    )
    await db.execute(stmt)
    await db.commit()

    return LlmConfigResponse(
        provider=cfg.get("provider", settings.llm_provider),
        model=cfg.get("model", settings.llm_model),
        api_key_masked=_mask_api_key(cfg.get("api_key", settings.llm_api_key)),
        base_url=cfg.get("base_url", settings.llm_base_url),
    )
