import uuid as _uuid
from collections.abc import Iterable

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.roles import format_roles, nonassignable_roles


class RoleUpdateError(Exception):
    """Base for refusals to change a user's roles."""


class UnknownRoleError(RoleUpdateError):
    """A requested role can't be granted to a human — either not in the
    catalogue at all, or a synthetic actor like SYSTEM."""

    def __init__(self, roles: set[str]):
        self.roles = roles
        super().__init__(f"cannot assign role(s): {sorted(roles)}")


class LastRoleHolderError(RoleUpdateError):
    """Removing this role would leave no admin able to perform it."""

    def __init__(self, role: str):
        self.role = role
        super().__init__(
            f"cannot remove the last admin holding the {role!r} role — "
            "grant it to another admin first"
        )


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
    async def get_by_id(db: AsyncSession, user_id: str | _uuid.UUID) -> User | None:
        uid = _uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        result = await db.execute(select(User).where(User.id == uid))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(db: AsyncSession) -> list[User]:
        result = await db.execute(select(User).order_by(User.created_at))
        return list(result.scalars().all())

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
        roles: Iterable[str] | None = None,
    ) -> User:
        user = User(
            email=UserService._normalize_email(email),
            password_hash=password_hash,
            is_admin=is_admin,
            roles=format_roles(roles or ()),
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
    async def set_roles(
        db: AsyncSession,
        user: User,
        roles: Iterable[str],
    ) -> User:
        """Replace `user`'s lifecycle roles, refusing two unsafe outcomes.

        - **Unknown role** — a role not in the catalogue (`app/roles.py`) would
          be dead weight no spec references; reject it.
        - **Last role holder** — removing a role this admin is the *only* admin
          to hold would strand every entity that needs it (e.g. drop the last
          `finance` admin and approved invoices can never be paid). Only admins
          count as holders, since only admins can fire transitions.

        The guard mirrors the admin-users "don't remove the last active admin"
        rule, applied per role instead of to the admin flag itself.
        """
        new = frozenset(roles)
        bad = nonassignable_roles(new)
        if bad:
            raise UnknownRoleError(bad)

        removed = user.role_set - new
        if removed and user.is_admin:
            others = await UserService.list_all(db)
            other_admin_roles = [
                u.role_set for u in others if u.is_admin and u.id != user.id
            ]
            for role in removed:
                if not any(role in rs for rs in other_admin_roles):
                    raise LastRoleHolderError(role)

        user.roles = format_roles(new)
        await db.commit()
        await db.refresh(user)
        return user
