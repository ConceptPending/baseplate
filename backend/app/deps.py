from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db


async def get_current_admin(access_token: str | None = Cookie(default=None)) -> str:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = jwt.decode(
            access_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        username: str | None = payload.get("sub")
        exp = payload.get("exp")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Token expired")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
