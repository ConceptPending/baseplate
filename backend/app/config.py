import sys

import structlog
from pydantic_settings import BaseSettings

logger = structlog.get_logger()


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://myapp:myapp@localhost:5433/myapp"
    admin_username: str = "admin"
    admin_password_hash: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours
    debug: bool = False
    cookie_secure: bool = True
    cors_origins: list[str] = ["http://localhost:3001"]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Startup validation — crash immediately if secrets are unsafe
_INSECURE_JWT_SECRETS = {"change-me-in-production", ""}

if not settings.debug:
    errors: list[str] = []
    if settings.jwt_secret in _INSECURE_JWT_SECRETS:
        errors.append(
            "JWT_SECRET is insecure (default or empty). Set a strong random value."
        )
    if not settings.admin_password_hash:
        errors.append(
            "ADMIN_PASSWORD_HASH is empty. Set a bcrypt hash for the admin password."
        )
    if (
        "localhost" in settings.database_url
        and "asyncpg://myapp:myapp@" in settings.database_url
    ):
        errors.append("DATABASE_URL appears to use default credentials.")
    if errors:
        for err in errors:
            logger.critical("startup_validation_failed", error=err)
        sys.exit(1)
