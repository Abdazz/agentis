from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class MemoryEntry(TimestampMixin, Base):
    """PostgreSQL reference record for a Qdrant memory point (spec §13 memory_entries)."""
    __tablename__ = "memory_entries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=False)
    qdrant_point_id: Mapped[UUID] = mapped_column(nullable=False, unique=True)
    source_task_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    importance: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.5")
    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="en")
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
