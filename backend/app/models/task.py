import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, Enum, ForeignKey, Integer, BigInteger, Boolean, JSON, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class TaskStatus(str, enum.Enum):
    submitted = "submitted"
    planning = "planning"
    running = "running"
    waiting_for_input = "waiting_for_input"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TaskStepType(str, enum.Enum):
    think = "think"
    tool_call = "tool_call"
    tool_result = "tool_result"
    reflect = "reflect"
    plan_update = "plan_update"
    user_input = "user_input"
    context_summarized = "context_summarized"
    report = "report"
    hitl_requested = "hitl_requested"


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    organization_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    goal: Mapped[str] = mapped_column(String(10000), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"), nullable=False, default=TaskStatus.submitted
    )
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="fr")
    plan: Mapped[Optional[dict]] = mapped_column(JSON)
    allowed_tools: Mapped[Optional[list]] = mapped_column(JSON)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    result_summary: Mapped[Optional[str]] = mapped_column(String)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000))
    error_code: Mapped[Optional[str]] = mapped_column(String(50))
    partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_webhook: Mapped[Optional[str]] = mapped_column(String(500))
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list["TaskStep"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tasks_user_status", "user_id", "status", "created_at"),
        Index("idx_tasks_status", "status", postgresql_where=text("deleted_at IS NULL")),
        Index("idx_tasks_active", "deleted_at", postgresql_where=text("deleted_at IS NULL")),
        Index("idx_tasks_org", "organization_id", "created_at"),
    )


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[TaskStepType] = mapped_column(Enum(TaskStepType, name="task_step_type"), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    task: Mapped["Task"] = relationship(back_populates="steps")

    __table_args__ = (
        Index("idx_task_steps_task", "task_id", "step_number"),
        UniqueConstraint("task_id", "step_number", name="uq_task_step_number"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    task: Mapped["Task"] = relationship(back_populates="artifacts")

    __table_args__ = (
        Index("idx_artifacts_task", "task_id"),
        Index("idx_artifacts_expiry", "expires_at", postgresql_where=text("deleted_at IS NULL")),
    )
