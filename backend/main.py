"""FastAPI application entry point for ulfweb."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import settings
from backend.database import init_database
from backend.routers import admin, chat, conversations, documents, models, settings as settings_router, translate


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize database on startup
    await init_database()
    yield


app = FastAPI(
    title="ulfweb",
    description="Chat web application for llama.cpp",
    version="1.0.0",
    lifespan=lifespan
)

# Include API routers
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(settings_router.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(translate.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")

# Serve static files
frontend_path = Path(__file__).parent.parent / "frontend"
app.mount("/css", StaticFiles(directory=frontend_path / "css"), name="css")
app.mount("/js", StaticFiles(directory=frontend_path / "js"), name="js")
app.mount("/images", StaticFiles(directory=frontend_path / "images"), name="images")


@app.get("/")
async def serve_index():
    """Serve the main HTML page."""
    return FileResponse(frontend_path / "index.html")


@app.get("/admin")
async def serve_admin():
    """Serve the admin HTML page."""
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
        reload=True
    )
