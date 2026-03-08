"""FastAPI application entry point for ulfweb."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from backend.auth import require_admin

from backend.config import settings
from backend.database import init_database
from backend.routers import admin, auth, backup, chat, conversations, documents, models, settings as settings_router, stt, translate, tts, update, users, vault
from backend.services.llama_manager import llama_manager
from backend.services.backup_service import backup_service
from backend.services import storage

logger = logging.getLogger("ulfweb")

# Read version from VERSION file
_version_file = Path(__file__).parent.parent / "VERSION"
APP_VERSION = _version_file.read_text().strip() if _version_file.exists() else "0.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize database on startup (also initializes encryption key)
    await init_database()

    # Encrypt existing vault files if needed
    vault.migrate_vault_files()

    # Auto-start servers with autoload enabled
    admin_cfg = await storage.get_admin_settings()
    servers = await storage.list_servers()
    for server in servers:
        if server.active and server.autoload and server.model_path:
            logger.info("Autoloading server: %s", server.friendly_name)
            try:
                await llama_manager.start_server(
                    server.id, server.model_path, server.url,
                    parallel=server.parallel, ctx_size=server.ctx_size,
                    backend=admin_cfg.llm_backend
                )
            except Exception as e:
                logger.error("Failed to autoload server %s: %s", server.friendly_name, e)

    # Log encryption status
    if settings.encryption.enabled:
        logger.warning(
            "Encryption at rest ENABLED — key file: %s — "
            "BACK UP THIS FILE SEPARATELY. If lost, all data is unrecoverable.",
            settings.encryption.key_file,
        )
    else:
        logger.info("Encryption at rest is DISABLED")

    # Start backup scheduler
    backup_service.start_scheduler()

    yield
    # Cleanup
    backup_service.stop_scheduler()
    llama_manager.cleanup()


app = FastAPI(
    title="ulfweb",
    description="Chat web application for llama.cpp",
    version=APP_VERSION,
    lifespan=lifespan
)

# Include API routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(settings_router.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(translate.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(tts.router, prefix="/api/v1")
app.include_router(stt.router, prefix="/api/v1")
app.include_router(vault.router, prefix="/api/v1")
app.include_router(backup.router, prefix="/api/v1")
app.include_router(update.router, prefix="/api/v1")

# Serve static files
frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/css", StaticFiles(directory=frontend_path / "css"), name="css")
app.mount("/js", StaticFiles(directory=frontend_path / "js"), name="js")
app.mount("/images", StaticFiles(directory=frontend_path / "images"), name="images")


@app.get("/")
async def serve_index():
    """Serve the main HTML page."""
    return FileResponse(frontend_path / "index.html")


@app.get("/login")
async def serve_login():
    """Serve the login HTML page."""
    return FileResponse(frontend_path / "login.html")


@app.get("/admin")
async def serve_admin(request: Request):
    """Serve the admin HTML page (admin users only)."""
    try:
        await require_admin(request)
    except Exception:
        return RedirectResponse(url="/")
    return FileResponse(frontend_path / "admin.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": APP_VERSION}


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="ULF Web server")
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload for development",
    )
    args = parser.parse_args()

    run_kwargs = {
        "host": settings.server.host,
        "port": settings.server.port,
    }
    if args.reload:
        run_kwargs["reload"] = True
        run_kwargs["reload_excludes"] = ["data/*"]

    uvicorn.run("backend.main:app", **run_kwargs)
