"""Admin endpoints for site-wide configuration."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.models import AdminSettings, AdminSettingsUpdate, Server, ServerCreate, ServerUpdate
from backend.services.llama_manager import llama_manager
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


@router.get("/models")
async def get_available_models():
    """List available .gguf model files from the configured models directory."""
    import re

    models_path = settings.models.path

    if not models_path:
        return {"models": [], "configured": False}

    models_dir = Path(models_path)
    if not models_dir.exists() or not models_dir.is_dir():
        return {"models": [], "configured": True, "error": f"Models directory not found: {models_path}"}

    models = []
    min_size = 100 * 1024 * 1024  # 100 MB
    # Pattern to match split model parts (e.g., -00002-of-00003.gguf)
    split_part_pattern = re.compile(r'-0000[2-9]-of-\d+\.gguf$|000[1-9][0-9]-of-\d+\.gguf$')
    # Pattern to match first part of split models (e.g., -00001-of-00003.gguf)
    first_part_pattern = re.compile(r'-00001-of-(\d+)\.gguf$')

    for gguf_file in models_dir.glob("*.gguf"):
        # Exclude mmproj files (vision projectors)
        if "mmproj" in gguf_file.name.lower():
            continue
        # Exclude non-first parts of split models (keep only -00001-of-XXXXX)
        if split_part_pattern.search(gguf_file.name):
            continue

        # Check if this is a split model (first part)
        first_part_match = first_part_pattern.search(gguf_file.name)
        if first_part_match:
            # Calculate total size across all parts
            num_parts = int(first_part_match.group(1))
            size = 0
            for i in range(1, num_parts + 1):
                part_name = first_part_pattern.sub(f'-{i:05d}-of-{num_parts:05d}.gguf', gguf_file.name)
                part_path = models_dir / part_name
                if part_path.exists():
                    size += part_path.stat().st_size
        else:
            size = gguf_file.stat().st_size

        # Only include models larger than 100 MB
        if size < min_size:
            continue
        models.append({
            "filename": gguf_file.name,
            "path": str(gguf_file),
            "size_bytes": size
        })

    # Sort by filename
    models.sort(key=lambda m: m["filename"].lower())

    return {"models": models, "configured": True}


@router.get("/servers", response_model=list[Server])
async def get_servers():
    """List all servers."""
    return await list_servers()


@router.get("/servers/active", response_model=list[Server])
async def get_active_servers():
    """List only active servers with running processes (for chat dropdown)."""
    servers = await list_servers(active_only=True)
    return [s for s in servers if llama_manager.get_status(s.id)]


@router.post("/servers", response_model=Server)
async def add_server(data: ServerCreate):
    """Add a new server."""
    server = await create_server(
        friendly_name=data.friendly_name,
        url=data.url,
        active=data.active,
        model_path=data.model_path,
        parallel=data.parallel,
        ctx_size=data.ctx_size
    )

    # Start llama.cpp process if server is active and has a model path
    if server.active and server.model_path:
        await llama_manager.start_server(
            server.id, server.model_path, server.url, server.parallel, server.ctx_size
        )

    return server


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
    old_server = await get_server(server_id)
    if not old_server:
        raise HTTPException(status_code=404, detail="Server not found")

    updates = data.model_dump(exclude_unset=True)
    new_server = await update_server(server_id, updates)

    # Handle process control based on changes
    active_changed = "active" in updates and updates["active"] != old_server.active
    parallel_changed = "parallel" in updates and updates["parallel"] != old_server.parallel
    model_path_changed = "model_path" in updates and updates["model_path"] != old_server.model_path
    ctx_size_changed = "ctx_size" in updates and updates["ctx_size"] != old_server.ctx_size

    if active_changed:
        if new_server.active:
            # Server activated - start process
            if new_server.model_path:
                await llama_manager.start_server(
                    server_id, new_server.model_path, new_server.url, new_server.parallel, new_server.ctx_size
                )
        else:
            # Server deactivated - stop process
            await llama_manager.stop_server(server_id)
    elif new_server.active and (parallel_changed or model_path_changed or ctx_size_changed):
        # Server is active and parallel/model/ctx_size changed - restart
        if new_server.model_path:
            await llama_manager.restart_server(
                server_id, new_server.model_path, new_server.url, new_server.parallel, new_server.ctx_size
            )

    return new_server


@router.delete("/servers/{server_id}")
async def delete_server_by_id(server_id: int):
    """Delete a server."""
    # Stop any running process first
    await llama_manager.stop_server(server_id)

    if not await delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")
    return {"status": "deleted"}


@router.post("/servers/{server_id}/start")
async def start_server_process(server_id: int):
    """Start a server's llama.cpp process."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not server.model_path:
        raise HTTPException(status_code=400, detail="Server has no model path configured")

    success = await llama_manager.start_server(
        server_id, server.model_path, server.url, server.parallel, server.ctx_size
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to start server process")

    return {"status": "started"}


@router.post("/servers/{server_id}/stop")
async def stop_server_process(server_id: int):
    """Stop a server's llama.cpp process."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    success = await llama_manager.stop_server(server_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to stop server process")

    return {"status": "stopped"}


@router.post("/servers/{server_id}/restart")
async def restart_server_process(server_id: int):
    """Restart a server's llama.cpp process."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not server.model_path:
        raise HTTPException(status_code=400, detail="Server has no model path configured")

    if not server.active:
        raise HTTPException(status_code=400, detail="Server is not active")

    success = await llama_manager.restart_server(
        server_id, server.model_path, server.url, server.parallel, server.ctx_size
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to restart server process")

    return {"status": "restarted"}


@router.get("/servers/{server_id}/status")
async def get_server_process_status(server_id: int):
    """Get the process status of a server."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    running = llama_manager.get_status(server_id)
    return {"server_id": server_id, "process_running": running}


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
