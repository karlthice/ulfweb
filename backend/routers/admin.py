"""Admin endpoints for site-wide configuration."""

import asyncio
import os
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.auth import get_client_ip, require_admin
from backend.config import settings
from backend.models import AdminSettings, AdminSettingsUpdate, Server, ServerCreate, ServerUpdate
from backend.services.llama_manager import llama_manager
from backend.services.system_info import get_system_ram, get_gpu_vram, get_process_memory
from backend.services.storage import (
    list_servers,
    get_server,
    create_server,
    update_server,
    delete_server,
    get_admin_settings,
    update_admin_settings,
    log_activity,
    get_activity_log,
    get_usage_stats,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# Regex patterns for split GGUF model files (compiled once at module level)
_SPLIT_PART_PATTERN = re.compile(r'-0000[2-9]-of-\d+\.gguf$|-000[1-9][0-9]-of-\d+\.gguf$')
_FIRST_PART_PATTERN = re.compile(r'-00001-of-(\d+)\.gguf$')


def _scan_model_dir(models_dir: Path) -> list[dict]:
    """Scan a single directory for .gguf model files, combining split model sizes."""
    results = []
    for f in models_dir.glob("*.gguf"):
        if "mmproj" in f.name.lower():
            continue
        if _SPLIT_PART_PATTERN.search(f.name):
            continue

        stat = f.stat()
        first_part_match = _FIRST_PART_PATTERN.search(f.name)
        if first_part_match:
            num_parts = int(first_part_match.group(1))
            size = 0
            for i in range(1, num_parts + 1):
                part_name = _FIRST_PART_PATTERN.sub(f'-{i:05d}-of-{num_parts:05d}.gguf', f.name)
                try:
                    size += (models_dir / part_name).stat().st_size
                except OSError:
                    pass
        else:
            size = stat.st_size

        results.append({
            "path": f,
            "name": f.name,
            "size_bytes": size,
            "mtime": stat.st_mtime,
        })
    return results


def _scan_model_files(models_path: str) -> list[dict]:
    """Scan one or more comma-separated directories for .gguf model files."""
    results = []
    seen = set()
    for raw_dir in models_path.split(","):
        d = Path(raw_dir.strip())
        if d.exists() and d.is_dir():
            for m in _scan_model_dir(d):
                if m["name"] not in seen:
                    seen.add(m["name"])
                    results.append(m)
    return results


def _find_free_port() -> int:
    """Find a free port by letting the OS assign one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@router.get("/system-info")
async def system_info():
    """Get system RAM, GPU VRAM, and per-model memory usage."""
    ram = get_system_ram()
    gpu = get_gpu_vram()

    models = []
    for server_id, proc in llama_manager.processes.items():
        if proc.poll() is not None:
            continue  # process has exited

        server = await get_server(server_id)
        if not server:
            continue

        mem = get_process_memory(proc.pid)
        if mem is None:
            continue

        # Determine memory mode
        has_vram = mem["vram_bytes"] > 0
        has_gtt = mem["gtt_bytes"] > 0
        if has_vram and has_gtt:
            memory_mode = "vram_and_ram"
        elif has_vram:
            memory_mode = "vram_only"
        else:
            memory_mode = "ram_only"

        model_file = server.model_path.rsplit("/", 1)[-1] if server.model_path else None

        models.append({
            "server_id": server_id,
            "server_name": server.friendly_name,
            "model_file": model_file,
            "pid": proc.pid,
            "ram_bytes": mem["ram_bytes"],
            "vram_bytes": mem["vram_bytes"],
            "gtt_bytes": mem["gtt_bytes"],
            "memory_mode": memory_mode,
        })

    return {"ram": ram, "gpu": gpu, "models": models}


@router.get("/models")
async def get_available_models():
    """List available .gguf model files from the configured models directories."""
    models_path = settings.models.path

    if not models_path:
        return {"models": [], "configured": False}

    min_size = 100 * 1024 * 1024  # 100 MB
    models = [
        {"filename": m["name"], "path": str(m["path"]), "size_bytes": m["size_bytes"]}
        for m in _scan_model_files(models_path)
        if m["size_bytes"] >= min_size
    ]

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
async def add_server(data: ServerCreate, request: Request):
    """Add a new server (admin only)."""
    await require_admin(request)
    url = data.url
    if not url:
        port = _find_free_port()
        url = f"http://localhost:{port}"

    server = await create_server(
        friendly_name=data.friendly_name,
        url=url,
        active=data.active,
        autoload=data.autoload,
        model_path=data.model_path,
        parallel=data.parallel,
        ctx_size=data.ctx_size
    )

    # Start llama.cpp process if server is active and has a model path
    if server.active and server.model_path:
        await llama_manager.start_server(
            server.id, server.model_path, server.url, server.parallel, server.ctx_size
        )

    ip = get_client_ip(request)
    await log_activity(ip, "admin.server.create", f"Created server '{server.friendly_name}'")
    return server


@router.get("/servers/{server_id}", response_model=Server)
async def get_server_by_id(server_id: int):
    """Get a server by ID."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


@router.put("/servers/{server_id}", response_model=Server)
async def update_server_by_id(server_id: int, data: ServerUpdate, request: Request):
    """Update a server (admin only)."""
    await require_admin(request)
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

    ip = get_client_ip(request)
    await log_activity(ip, "admin.server.update", f"Updated server '{new_server.friendly_name}'")
    return new_server


@router.delete("/servers/{server_id}")
async def delete_server_by_id(server_id: int, request: Request):
    """Delete a server (admin only)."""
    await require_admin(request)
    server = await get_server(server_id)
    # Stop any running process first
    await llama_manager.stop_server(server_id)

    if not await delete_server(server_id):
        raise HTTPException(status_code=404, detail="Server not found")

    ip = get_client_ip(request)
    name = server.friendly_name if server else f"ID {server_id}"
    await log_activity(ip, "admin.server.delete", f"Deleted server '{name}'")
    return {"status": "deleted"}


@router.post("/servers/{server_id}/start")
async def start_server_process(server_id: int, request: Request):
    """Start a server's llama.cpp process (admin only)."""
    await require_admin(request)
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

    ip = get_client_ip(request)
    await log_activity(ip, "admin.server.start", f"Started server '{server.friendly_name}'")
    return {"status": "started"}


@router.post("/servers/{server_id}/stop")
async def stop_server_process(server_id: int, request: Request):
    """Stop a server's llama.cpp process (admin only)."""
    await require_admin(request)
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    success = await llama_manager.stop_server(server_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to stop server process")

    ip = get_client_ip(request)
    await log_activity(ip, "admin.server.stop", f"Stopped server '{server.friendly_name}'")
    return {"status": "stopped"}


@router.post("/servers/{server_id}/restart")
async def restart_server_process(server_id: int, request: Request):
    """Restart a server's llama.cpp process (admin only)."""
    await require_admin(request)
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

    ip = get_client_ip(request)
    await log_activity(ip, "admin.server.restart", f"Restarted server '{server.friendly_name}'")
    return {"status": "restarted"}


@router.get("/servers/{server_id}/log")
async def get_server_log(server_id: int, tail: int = 200):
    """Get the log file for a server process."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    log_path = Path("data/logs") / f"llama-server-{server_id}.log"
    filename = log_path.name
    if not log_path.exists():
        return {"log": "", "filename": filename}

    lines = log_path.read_text(errors="replace").splitlines()
    if tail > 0:
        lines = lines[-tail:]
    return {"log": "\n".join(lines), "filename": filename}


@router.get("/servers/{server_id}/status")
async def get_server_process_status(server_id: int):
    """Get the process status of a server."""
    server = await get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    running = llama_manager.get_status(server_id)
    return {"server_id": server_id, "process_running": running}


@router.post("/restart")
async def restart_ulfweb(request: Request):
    """Restart the entire ULF Web application (admin only).

    Touches main.py to trigger uvicorn's file-change reloader.
    """
    await require_admin(request)
    ip = get_client_ip(request)
    await log_activity(ip, "admin.restart", "Restarted ULF Web application")

    def _do_restart():
        llama_manager.cleanup()
        # Touch a source file to trigger uvicorn's WatchFiles reloader
        main_py = Path(__file__).parent.parent / "main.py"
        main_py.touch()

    asyncio.get_event_loop().call_later(0.5, _do_restart)
    return {"status": "restarting"}


# Admin settings endpoints
@router.get("/settings", response_model=AdminSettings)
async def get_settings():
    """Get admin settings."""
    return await get_admin_settings()


@router.put("/settings", response_model=AdminSettings)
async def update_settings(data: AdminSettingsUpdate, request: Request):
    """Update admin settings (admin only)."""
    await require_admin(request)
    updates = data.model_dump(exclude_unset=True)
    result = await update_admin_settings(updates)
    ip = get_client_ip(request)
    changed = ", ".join(updates.keys())
    await log_activity(ip, "admin.settings.update", f"Updated admin settings: {changed}")
    return result


@router.get("/date-format")
async def get_date_format():
    """Get the configured date format (public endpoint)."""
    settings = await get_admin_settings()
    return {"date_format": settings.date_format}


# Activity log endpoints
@router.get("/activity-log")
async def get_activity_log_entries(
    offset: int = 0,
    limit: int = 50,
    action_type: str | None = None,
    user_ip: str | None = None,
    search: str | None = None,
):
    """Get paginated activity log entries with optional filters."""
    entries, total = await get_activity_log(offset, limit, action_type, user_ip, search)
    return {"entries": entries, "total": total, "offset": offset, "limit": limit}


@router.get("/activity-log/action-types")
async def get_activity_log_action_types():
    """Get distinct action types from the activity log."""
    from backend.database import get_db
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT DISTINCT action_type FROM activity_log ORDER BY action_type"
        )
        rows = await cursor.fetchall()
        return {"action_types": [row["action_type"] for row in rows]}


@router.get("/usage")
async def get_usage():
    """Get usage statistics for the admin dashboard."""
    return await get_usage_stats()


@router.get("/file-info")
async def get_file_info():
    """Get modification dates and sizes for project and model files."""
    project_root = Path(__file__).parent.parent.parent
    now = time.time()

    # Project files: scan backend/ and frontend/ for source files
    project_files = []
    extensions = {".py", ".js", ".css", ".html", ".yaml", ".yml"}
    for subdir in ["backend", "frontend"]:
        scan_dir = project_root / subdir
        if not scan_dir.exists():
            continue
        for f in scan_dir.rglob("*"):
            if f.is_file() and f.suffix in extensions and "vendor" not in f.parts:
                stat = f.stat()
                project_files.append({
                    "name": str(f.relative_to(project_root)),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "age_seconds": now - stat.st_mtime,
                })

    project_files.sort(key=lambda f: f["age_seconds"])

    # Model files: use shared scanner
    model_files = []
    models_path = settings.models.path
    if models_path:
        model_files = [
            {
                "name": m["name"],
                "size_bytes": m["size_bytes"],
                "modified": datetime.fromtimestamp(m["mtime"], tz=timezone.utc).isoformat(),
                "age_seconds": now - m["mtime"],
            }
            for m in _scan_model_files(models_path)
        ]
        model_files.sort(key=lambda f: f["age_seconds"])

    return {"project_files": project_files, "model_files": model_files}
