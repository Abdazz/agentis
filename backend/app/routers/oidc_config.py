import structlog
import uuid as uuid_lib
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AnyHttpUrl, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_operator
from app.config import settings
from app.database import get_db
from app.models.oidc import OidcConfig
from app.models.org import Organization
from app.models.user import User

router = APIRouter(prefix="/admin/organizations", tags=["oidc"])

log = structlog.get_logger()

REDACTED = "***"


class OidcConfigRequest(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    discovery_url: AnyHttpUrl
    enabled: bool = False


class OidcConfigResponse(BaseModel):
    id: str
    org_id: str
    provider: str
    client_id: str
    client_secret: str  # always "***"
    discovery_url: str
    enabled: bool


def _encrypt_secret(secret: str) -> str:
    key = settings.fernet_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encryption key not configured (AGENTIS_FERNET_KEY)",
        )
    return Fernet(key.encode()).encrypt(secret.encode()).decode()


def _to_response(cfg: OidcConfig) -> OidcConfigResponse:
    return OidcConfigResponse(
        id=str(cfg.id),
        org_id=str(cfg.org_id),
        provider=cfg.provider,
        client_id=cfg.client_id,
        client_secret=REDACTED,
        discovery_url=cfg.discovery_url,
        enabled=cfg.enabled,
    )


async def _get_org_or_404(org_id: str, db: AsyncSession) -> Organization:
    try:
        org_uuid = uuid_lib.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    result = await db.execute(
        select(Organization).where(
            Organization.id == org_uuid,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.post("/{org_id}/oidc", response_model=OidcConfigResponse, status_code=201)
async def upsert_oidc_config(
    org_id: str,
    body: OidcConfigRequest,
    _: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the OIDC SSO configuration for an organization (operator-only)."""
    org = await _get_org_or_404(org_id, db)

    encrypted_secret = _encrypt_secret(body.client_secret)

    result = await db.execute(
        select(OidcConfig).where(OidcConfig.org_id == org.id).with_for_update()
    )
    cfg = result.scalar_one_or_none()

    discovery_url = str(body.discovery_url)
    if cfg is None:
        cfg = OidcConfig(
            org_id=org.id,
            provider=body.provider,
            client_id=body.client_id,
            client_secret=encrypted_secret,
            discovery_url=discovery_url,
            enabled=body.enabled,
        )
        db.add(cfg)
    else:
        cfg.provider = body.provider
        cfg.client_id = body.client_id
        cfg.client_secret = encrypted_secret
        cfg.discovery_url = discovery_url
        cfg.enabled = body.enabled

    await db.commit()
    await db.refresh(cfg)
    return _to_response(cfg)


@router.get("/{org_id}/oidc", response_model=OidcConfigResponse)
async def get_oidc_config(
    org_id: str,
    _: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
):
    """Get the OIDC SSO configuration for an organization (operator-only)."""
    org = await _get_org_or_404(org_id, db)

    result = await db.execute(
        select(OidcConfig).where(OidcConfig.org_id == org.id)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OIDC config not found")
    return _to_response(cfg)
