from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_id: Mapped[Optional[UUID]]
    organization_id: Mapped[Optional[UUID]]
    session_id: Mapped[Optional[UUID]]
    task_id: Mapped[Optional[UUID]]
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    outcome: Mapped[Optional[str]] = mapped_column(String(20))
    request_id: Mapped[Optional[UUID]]

    __table_args__ = (
        Index("idx_audit_user_time", "user_id", "created_at"),
        Index("idx_audit_task", "task_id", "created_at"),
        Index("idx_audit_event_type", "event_type", "created_at"),
    )
