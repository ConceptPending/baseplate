from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.roles import parse_roles


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    is_admin: bool
    # Lifecycle roles, surfaced so the frontend can show/hide the actions a
    # user is authorised for. Serialised from the stored CSV into a list.
    roles: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("roles", mode="before")
    @classmethod
    def _split_roles(cls, v: object) -> list[str]:
        # The ORM attribute is a CSV string; accept that (or an already-parsed
        # list) and normalise to a sorted list.
        if isinstance(v, str):
            return sorted(parse_roles(v))
        if v is None:
            return []
        return sorted(v)  # type: ignore[arg-type]


class RoleAssignment(BaseModel):
    """Full replacement of a user's lifecycle roles. Unknown roles and unsafe
    removals are rejected by the service, not here."""

    roles: list[str]
