"""User settings endpoints."""

from fastapi import APIRouter, Request

from backend.models import UserSettings, UserSettingsUpdate
from backend.services.storage import (
    get_or_create_user,
    get_user_settings,
    update_user_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.get("", response_model=UserSettings)
async def get_settings(request: Request):
    """Get the current user's settings."""
    ip = get_client_ip(request)
    user_id = await get_or_create_user(ip)
    return await get_user_settings(user_id)


@router.put("", response_model=UserSettings)
async def update_settings(data: UserSettingsUpdate, request: Request):
    """Update the current user's settings."""
    ip = get_client_ip(request)
    user_id = await get_or_create_user(ip)
    updates = data.model_dump(exclude_unset=True)
    return await update_user_settings(user_id, updates)
