"""Admin user-management routes.

Currently scoped to viewing users and assigning lifecycle roles — the piece the
invoice review workflow needs. The admin-users recipe
(docs/recipes/admin-users.md) extends this same router/service with create,
deactivate, and promote/demote.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin
from app.schemas.user import RoleAssignment, UserResponse
from app.services.users import (
    LastRoleHolderError,
    UnknownRoleError,
    UserService,
)

router = APIRouter(
    prefix="/api/admin/users",
    tags=["users"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    """All users with their roles — so an admin can see who can do what before
    assigning."""
    return await UserService.list_all(db)


@router.put("/{user_id}/roles", response_model=UserResponse)
async def set_user_roles(
    user_id: uuid.UUID,
    data: RoleAssignment,
    db: AsyncSession = Depends(get_db),
):
    """Replace a user's lifecycle roles. Refuses unknown roles (422) and any
    change that would remove the last admin holding a role (409)."""
    user = await UserService.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        return await UserService.set_roles(db, user, data.roles)
    except UnknownRoleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LastRoleHolderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
