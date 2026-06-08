from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.lifecycle import LifecycleSpecResponse

__all__ = [
    "SubmissionCreate",
    "SubmissionResponse",
    "SubmissionTransition",
    "LifecycleSpecResponse",
]


class SubmissionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    message: str = Field(min_length=1, max_length=10_000)


class SubmissionResponse(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    message: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SubmissionTransition(BaseModel):
    action: str = Field(min_length=1)
