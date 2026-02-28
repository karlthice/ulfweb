"""User settings endpoints."""

from fastapi import APIRouter, Request

from backend.auth import get_client_ip, require_user
from backend.models import UserSettings, UserSettingsUpdate
from backend.services.storage import (
    get_user_settings,
    log_activity,
    update_user_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(request: Request):
    """Get the current user's settings, including usertype."""
    user = await require_user(request)
    settings = await get_user_settings(user["id"])
    result = settings.model_dump()
    result["usertype"] = user["usertype"]
    return result


@router.put("", response_model=UserSettings)
async def update_settings(data: UserSettingsUpdate, request: Request):
    """Update the current user's settings."""
    user = await require_user(request)
    ip = get_client_ip(request)
    updates = data.model_dump(exclude_unset=True)
    result = await update_user_settings(user["id"], updates)
    changed = ", ".join(updates.keys())
    await log_activity(ip, "settings.update", f"Updated settings: {changed}", user["id"])
    return result
