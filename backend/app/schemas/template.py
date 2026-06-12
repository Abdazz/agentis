from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    goal_template: str = Field(min_length=1)
    category: Optional[str] = Field(None, max_length=100)
    is_public: bool = True


class TemplateResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    goal_template: str
    category: Optional[str] = None
    created_by: Optional[UUID] = None
    is_public: bool
    created_at: datetime

    model_config = {"from_attributes": True}
