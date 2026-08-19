from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.services.scheduler import validate_cron, InvalidCronExpression


class ScheduledTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    goal_template: str = Field(min_length=1, max_length=10000)
    cron_expression: str = Field(min_length=1, max_length=100)
    language: Optional[str] = None
    allowed_tools: Optional[list[str]] = None
    max_iterations: Optional[int] = Field(None, ge=1, le=200)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v is not None and v not in ("en", "fr"):
            raise ValueError("language must be 'en' or 'fr'")
        return v

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v):
        try:
            validate_cron(v)
        except InvalidCronExpression as e:
            raise ValueError(str(e))
        return v


class ScheduledTaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    goal_template: Optional[str] = Field(None, min_length=1, max_length=10000)
    cron_expression: Optional[str] = Field(None, min_length=1, max_length=100)
    language: Optional[str] = None
    allowed_tools: Optional[list[str]] = None
    max_iterations: Optional[int] = Field(None, ge=1, le=200)
    is_active: Optional[bool] = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v):
        if v is None:
            return v
        try:
            validate_cron(v)
        except InvalidCronExpression as e:
            raise ValueError(str(e))
        return v


class ScheduledTaskResponse(BaseModel):
    id: UUID
    name: str
    goal_template: str
    cron_expression: str
    language: Optional[str] = None
    allowed_tools: Optional[list[str]] = None
    max_iterations: Optional[int] = None
    is_active: bool
    next_run_at: datetime
    last_run_at: Optional[datetime] = None
    last_task_id: Optional[UUID] = None
    last_status: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
