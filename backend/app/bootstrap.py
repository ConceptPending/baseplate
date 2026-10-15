import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.roles import HUMAN_ROLES
from app.services.users import UserService

logger = structlog.get_logger()


async def ensure_admin_user(db: AsyncSession) -> None:
    """Create the bootstrap admin user from env vars if no admin exists.

    Idempotent: runs on every startup, only writes when there are zero admins
    in the database. After the bootstrap admin exists, ADMIN_EMAIL and
    ADMIN_PASSWORD_HASH are unused — manage users via the DB.

    If env vars are missing in non-debug mode, startup validation has already
    crashed the app before we get here, so we can trust them when present.
    """
    admin_count = await UserService.count_admins(db)
    if admin_count > 0:
        return

    if not settings.admin_email or not settings.admin_password_hash:
        logger.warning(
            "admin_bootstrap_skipped",
            reason="no admins in DB and ADMIN_EMAIL / ADMIN_PASSWORD_HASH not set",
        )
        return

    # ADMIN_PASSWORD_HASH must be a bcrypt hash, not a plaintext password. Refuse
    # to seed an unloginnable/insecure admin from a misconfigured value.
    if not settings.admin_password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        logger.error(
            "admin_bootstrap_skipped",
            reason="ADMIN_PASSWORD_HASH is not a bcrypt hash (expected a $2b$… value). "
            "Generate one with `make hash-password`.",
        )
        return

    # The first admin holds every human role — otherwise a fresh install has
    # an admin who can reach the lifecycle UI but is 403'd from every
    # transition. Grant later admins their roles deliberately.
    user = await UserService.create(
        db,
        email=settings.admin_email,
        password_hash=settings.admin_password_hash,
        is_admin=True,
        roles=sorted(HUMAN_ROLES),
    )
    logger.info("admin_user_bootstrapped", user_id=str(user.id), email=user.email)
