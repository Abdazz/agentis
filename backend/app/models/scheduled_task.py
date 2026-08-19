"""Scheduled (recurring) task model — Manus-parity "Scheduled Tasks" feature.

A ScheduledTask is a template that gets materialized into a real Task on
each cron firing (via beat.run_due_scheduled_tasks), exactly the same way
a user submitting the goal by hand would — it goes through the normal
Task -> Celery -> orchestrator pipeline, so scheduled runs get the same
budgets, HITL gating, and observability as any other task.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ScheduledTask(TimestampMixin, Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal_template: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    allowed_tools: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    max_iterations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_task_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    last_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
