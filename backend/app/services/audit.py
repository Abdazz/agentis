"""Audit event persistence (spec §14 AUDIT-1)."""
from datetime import datetime, timezone
from typing import Optional
from app.database import AsyncSessionLocal
from app.models.audit import AuditLog


async def write_audit_event(
    actor_id: str,
    actor_email: str,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Persist a single audit event. Fire-and-forget — never raises."""
    event = AuditLog(
        created_at=datetime.now(timezone.utc),
        event_type=action,
        event_data={
            "actor_id": actor_id,
            "actor_email": actor_email,
            "resource_type": resource_type,
            "resource_id": resource_id,
            **(metadata or {}),
        },
    )
    try:
        async with AsyncSessionLocal() as session:
            session.add(event)
            await session.commit()
    except Exception:
        pass  # Audit failure must never block the main flow
