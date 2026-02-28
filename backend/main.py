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
from backend.routers import admin, auth, chat, conversations, documents, models, settings as settings_router, stt, translate, tts, users, vault
from backend.services.llama_manager import llama_manager

logger = logging.getLogger("ulfweb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize database on startup (also initializes encryption key)
    await init_database()

    # Encrypt existing vault files if needed
    vault.migrate_vault_files()

    # Log encryption status
    if settings.encryption.enabled:
        logger.warning(
            "Encryption at rest ENABLED — key file: %s — "
            "BACK UP THIS FILE SEPARATELY. If lost, all data is unrecoverable.",
            settings.encryption.key_file,
        )
    else:
        logger.info("Encryption at rest is DISABLED")

    yield
    # Cleanup llama.cpp processes on shutdown
    llama_manager.cleanup()


app = FastAPI(
    title="ulfweb",
    description="Chat web application for llama.cpp",
    version="1.0.0",
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
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
        reload_excludes=["data/*"],
    )
