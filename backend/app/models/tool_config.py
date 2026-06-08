from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class RegisteredTool(Base):
    __tablename__ = "tool_configs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    enabled_globally: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # None = allowed for all orgs; list of org UUID strings = restricted to those orgs
    allowed_orgs: Mapped[Optional[list]] = mapped_column(JSON)
    # builtin | mcp | openapi
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="builtin")
    mcp_url: Mapped[Optional[str]] = mapped_column(String(2048))
    openapi_spec_url: Mapped[Optional[str]] = mapped_column(String(2048))
    tool_metadata: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
