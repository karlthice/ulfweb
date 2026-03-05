"""Backup management endpoints."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.auth import get_client_ip, require_admin
from backend.services.backup_service import backup_service
from backend.services.llama_manager import llama_manager
from backend.services.storage import log_activity

logger = logging.getLogger("ulfweb")

router = APIRouter(prefix="/admin/backups", tags=["backups"])


class CreateBackupRequest(BaseModel):
    destination: Optional[str] = None


class RestoreBackupRequest(BaseModel):
    backup_path: str


# --- Public endpoint (needed for banner on all pages) ---

@router.get("/health")
async def backup_health():
    """Backup health status — public, used by the failure banner."""
    return backup_service.get_health()


# --- Admin endpoints ---

@router.get("/list")
async def list_backups(request: Request, directory: Optional[str] = None):
    """List backups in the default or specified directory."""
    await require_admin(request)
    try:
        backups = backup_service.list_backups(directory)
        return {"backups": backups}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status")
async def backup_status(request: Request):
    """Current backup status."""
    await require_admin(request)
    return {
        "in_progress": backup_service._backup_in_progress,
        "health": backup_service.get_health(),
    }


@router.post("/create")
async def create_backup(data: CreateBackupRequest, request: Request):
    """Create a new backup archive."""
    await require_admin(request)
    try:
        result = backup_service.create_backup(data.destination)
        ip = get_client_ip(request)
        dest = data.destination or "default"
        await log_activity(ip, "admin.backup.create", f"Created backup: {result['filename']} ({dest})")
        return result
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Backup creation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore")
async def restore_backup(data: RestoreBackupRequest, request: Request):
    """Restore from a backup archive, then restart the application."""
    await require_admin(request)
    try:
        result = backup_service.restore_backup(data.backup_path)
        ip = get_client_ip(request)
        await log_activity(ip, "admin.backup.restore", f"Restored backup: {result['filename']}")
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Backup restore failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # Trigger app restart after restore
    def _do_restart():
        llama_manager.cleanup()
        main_py = Path(__file__).parent.parent / "main.py"
        main_py.touch()

    asyncio.get_event_loop().call_later(0.5, _do_restart)
    return {**result, "restarting": True}


@router.delete("/delete")
async def delete_backup(request: Request, backup_path: str):
    """Delete a specific backup file."""
    await require_admin(request)
    try:
        deleted = backup_service.delete_backup(backup_path)
        if not deleted:
            raise HTTPException(status_code=404, detail="Backup not found")
        ip = get_client_ip(request)
        filename = Path(backup_path).name
        await log_activity(ip, "admin.backup.delete", f"Deleted backup: {filename}")
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Backup deletion failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
