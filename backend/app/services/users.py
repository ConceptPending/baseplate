from uuid import UUID

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class LastAdminError(Exception):
    """Refusal to deactivate or demote the last active admin."""


class UserService:
    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(
            select(User).where(User.email == UserService._normalize_email(email))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_admins(db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count()).select_from(User).where(User.is_admin.is_(True))
        )
        return int(result.scalar_one())

    @staticmethod
    async def create(
        db: AsyncSession,
        email: str,
        password_hash: str,
        is_admin: bool = False,
    ) -> User:
        user = User(
            email=UserService._normalize_email(email),
            password_hash=password_hash,
            is_admin=is_admin,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
        """Return the user iff the password matches. Returns None for both
        missing user and wrong password — callers MUST NOT distinguish the
        two cases to avoid user enumeration via response codes or messages."""
        user = await UserService.get_by_email(db, email)
        if not user:
            return None
        if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            return None
        return user

    @staticmethod
    async def list_all(db: AsyncSession) -> list[User]:
        result = await db.execute(select(User).order_by(User.email))
        return list(result.scalars().all())

    @staticmethod
    async def _active_admin_count(db: AsyncSession) -> int:
        result = await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.is_admin.is_(True), User.is_active.is_(True))
        )
        return int(result.scalar_one())

    @staticmethod
    async def set_active(
        db: AsyncSession, user_id: UUID, *, is_active: bool, actor_id: UUID
    ) -> User:
        if not is_active and user_id == actor_id:
            raise ValueError("Cannot deactivate yourself.")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found.")
        # Refuse to deactivate the only remaining active admin.
        if (
            not is_active
            and user.is_admin
            and user.is_active
            and await UserService._active_admin_count(db) <= 1
        ):
            raise LastAdminError("Refusing to deactivate the last active admin.")
        user.is_active = is_active
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def set_admin(
        db: AsyncSession, user_id: UUID, *, is_admin: bool, actor_id: UUID
    ) -> User:
        if not is_admin and user_id == actor_id:
            raise ValueError("Cannot remove your own admin role.")
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found.")
        if (
            not is_admin
            and user.is_admin
            and user.is_active
            and await UserService._active_admin_count(db) <= 1
        ):
            raise LastAdminError("Refusing to demote the last active admin.")
        user.is_admin = is_admin
        await db.commit()
        await db.refresh(user)
        return user
