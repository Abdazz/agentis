from datetime import datetime
from typing import Optional
from uuid import UUID
import uuid
from pydantic import BaseModel, Field, field_validator


class TaskOptions(BaseModel):
    max_iterations: Optional[int] = None
    allowed_tools: Optional[list[str]] = None
    notify_webhook: Optional[str] = None


class TaskCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=10000)
    language: Optional[str] = None
    options: TaskOptions = Field(default_factory=TaskOptions)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v is not None and v not in ("en", "fr"):
            raise ValueError("language must be 'en' or 'fr'")
        return v


class TaskResponse(BaseModel):
    id: UUID
    goal: str
    status: str
    language: str
    plan: Optional[dict] = None
    max_iterations: int
    allowed_tools: Optional[list[str]] = None
    result_summary: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    partial: bool
    total_tokens: int
    total_steps: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    stream_url: Optional[str] = None
    parent_task_id: Optional[uuid.UUID] = None
    agent_role: Optional[str] = None

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    next_cursor: Optional[str] = None
    has_more: bool
    total: int


class TaskListResponse(BaseModel):
    data: list[TaskResponse]
    pagination: PaginationMeta
