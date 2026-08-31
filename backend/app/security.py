"""
Minimal auth: if ADMIN_API_KEY is set in the environment, mutating admin
endpoints require `Authorization: Bearer <key>`. If it's left blank (the
default, for local development), everything is open. Swap this for real
auth (school-login SSO, etc.) before deploying beyond a single trusted LAN.
"""
from fastapi import Header, HTTPException, status

from app.config import settings


async def require_admin(authorization: str | None = Header(default=None)) -> None:
    if not settings.admin_api_key:
        return  # auth disabled
    expected = f"Bearer {settings.admin_api_key}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing admin token")
