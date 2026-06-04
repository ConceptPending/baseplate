import bcrypt
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_admin
from app.models.user import User
from app.schemas.user import UserResponse
from app.services.users import LastAdminError, UserService

router = APIRouter(
    prefix="/api/admin/users",
    tags=["users"],
    dependencies=[Depends(get_current_admin)],
)


# An "invite" creates the user with a random initial password. The admin shares
# it out-of-band, or the user logs in via SSO if the OIDC recipe is applied. The
# initial password is intentionally NOT returned (no passwords-via-screenshot).
class InviteRequest(BaseModel):
    email: EmailStr
    is_admin: bool = True


class SetActiveRequest(BaseModel):
    is_active: bool


class SetAdminRequest(BaseModel):
    is_admin: bool


@router.get("", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    return await UserService.list_all(db)


@router.post("", response_model=UserResponse, status_code=201)
async def invite_user(data: InviteRequest, db: AsyncSession = Depends(get_db)):
    if await UserService.get_by_email(db, data.email):
        raise HTTPException(status_code=409, detail="User already exists")
    initial_password = secrets.token_urlsafe(16)
    pw_hash = bcrypt.hashpw(initial_password.encode(), bcrypt.gensalt()).decode()
    return await UserService.create(
        db, email=data.email, password_hash=pw_hash, is_admin=data.is_admin
    )


@router.patch("/{user_id}/active", response_model=UserResponse)
async def set_active(
    user_id: UUID,
    data: SetActiveRequest,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await UserService.set_active(
            db, user_id, is_active=data.is_active, actor_id=user.id
        )
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/{user_id}/admin", response_model=UserResponse)
async def set_admin(
    user_id: UUID,
    data: SetAdminRequest,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await UserService.set_admin(
            db, user_id, is_admin=data.is_admin, actor_id=user.id
        )
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
