"""Admin endpoints for site-wide configuration."""

from fastapi import APIRouter, HTTPException

from backend.models import AdminSettings, AdminSettingsUpdate, Server, ServerCreate, ServerUpdate
from backend.services.storage import (
    list_servers,
    get_server,
    create_server,
    update_server,
    delete_server,
    get_admin_settings,
    update_admin_settings,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/servers", response_model=list[Server])
async def get_servers():
    """List all servers."""
    return await list_servers()


@router.get("/servers/active", response_model=list[Server])
async def get_active_servers():
    """List only active servers (for chat dropdown)."""
    return await list_servers(active_only=True)


@router.post("/servers", response_model=Server)
async def add_server(data: ServerCreate):
    """Add a new server."""
    return await create_server(
        friendly_name=data.friendly_name,
        url=data.url,
        active=data.active
    )


@router.get("/servers/{server_id}", response_model=Server)
async def get_server_by_id(server_id: int):
    """Get a server by ID."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@router.put("/servers/{server_id}", response_model=Server)
async def update_server_by_id(server_id: int, data: ServerUpdate):
    """Update a server."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    updates = data.model_dump(exclude_unset=True)
    return await update_server(server_id, updates)


@router.delete("/servers/{server_id}")
async def delete_server_by_id(server_id: int):
    """Delete a server."""
    if not await delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")
    return {"status": "deleted"}


# Admin settings endpoints
@router.get("/settings", response_model=AdminSettings)
async def get_settings():
    """Get admin settings."""
    return await get_admin_settings()


@router.put("/settings", response_model=AdminSettings)
async def update_settings(data: AdminSettingsUpdate):
    """Update admin settings."""
    updates = data.model_dump(exclude_unset=True)
    return await update_admin_settings(updates)
