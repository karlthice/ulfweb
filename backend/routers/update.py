"""Update management endpoints — USB-based code updates and model imports."""

import asyncio
import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.auth import get_client_ip, require_admin
from backend.services.llama_manager import llama_manager
from backend.services.storage import log_activity
from backend.services.update_service import update_service

logger = logging.getLogger("ulfweb")

router = APIRouter(prefix="/admin/updates", tags=["updates"])


class ApplyUpdateRequest(BaseModel):
    package_path: str


class ImportModelRequest(BaseModel):
    source_path: str


# --- Public endpoint ---

@router.get("/version")
async def get_version():
    """Current application version — public."""
    return {"version": update_service.get_current_version()}


# --- Admin endpoints ---

@router.get("/scan")
async def scan_usb_drives(request: Request):
    """Scan for mounted USB drives."""
    await require_admin(request)
    drives = update_service.scan_media_mounts()
    return {"drives": drives}


@router.get("/scan-packages")
async def scan_packages(request: Request, usb_path: str):
    """Find update packages on a USB drive."""
    await require_admin(request)

    # Security: verify the path is under /media or /run/media
    real_path = os.path.realpath(usb_path)
    if not (real_path.startswith("/media/") or real_path.startswith("/run/media/")):
        raise HTTPException(status_code=400, detail="Path must be under /media/ or /run/media/")

    packages = update_service.scan_update_packages(usb_path)
    return {"packages": packages}


@router.get("/scan-models")
async def scan_models(request: Request, usb_path: str):
    """Find .gguf model files on a USB drive."""
    await require_admin(request)

    real_path = os.path.realpath(usb_path)
    if not (real_path.startswith("/media/") or real_path.startswith("/run/media/")):
        raise HTTPException(status_code=400, detail="Path must be under /media/ or /run/media/")

    models = update_service.scan_models(usb_path)
    return {"models": models}


@router.post("/apply")
async def apply_update(data: ApplyUpdateRequest, request: Request):
    """Apply a code update from a USB package, then restart."""
    await require_admin(request)
    ip = get_client_ip(request)

    try:
        result = update_service.apply_code_update(data.package_path)
        await log_activity(ip, "admin.update.apply", f"Applied update to version {result['version']}")
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Update failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # Schedule full process restart via os.execv
    def _do_restart():
        llama_manager.cleanup()
        os.execv(sys.executable, [sys.executable, "-m", "backend.main"])

    asyncio.get_event_loop().call_later(1.0, _do_restart)
    return result


@router.post("/import-model")
async def import_model(data: ImportModelRequest, request: Request):
    """Copy a model file from USB to the models directory."""
    await require_admin(request)
    ip = get_client_ip(request)

    try:
        result = update_service.import_model(data.source_path)
        await log_activity(ip, "admin.update.import_model", f"Imported model: {result['filename']}")
        return result
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Model import failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
