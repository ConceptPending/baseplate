from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config import settings
from app.deps import get_current_admin
from app.schemas.auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, response: Response):
    if body.username != settings.admin_username:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not settings.admin_password_hash:
        raise HTTPException(status_code=500, detail="Admin password not configured")

    if not _bcrypt.checkpw(
        body.password.encode(), settings.admin_password_hash.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    token = jwt.encode(
        {"sub": body.username, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
    return LoginResponse()


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}


@router.get("/me")
async def me(username: str = Depends(get_current_admin)):
    """Check auth status - requires valid cookie."""
    return {"username": username}
