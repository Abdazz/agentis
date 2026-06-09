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
