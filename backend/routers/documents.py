"""API routes for document collections and GraphRAG queries."""

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from backend.models import (
    Collection,
    CollectionCreate,
    CollectionUpdate,
    CollectionWithStats,
    Document,
    DocumentQuery,
    DocumentStatusResponse,
)
from backend.services import storage
from backend.services.graphrag import graphrag_service
from backend.services.storage import log_activity

router = APIRouter(prefix="/documents", tags=["documents"])


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# Collection endpoints
@router.get("/collections", response_model=list[CollectionWithStats])
async def list_collections():
    """List all collections with document counts."""
    return await storage.list_collections()


@router.post("/collections", response_model=Collection)
async def create_collection(data: CollectionCreate, request: Request):
    """Create a new collection (admin)."""
    try:
        collection = await storage.create_collection(data.name, data.description)
        ip = get_client_ip(request)
        await log_activity(ip, "document.collection.create", f"Created collection '{data.name}'")
        return collection
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=400, detail="Collection name already exists")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{collection_id}", response_model=CollectionWithStats)
async def get_collection(collection_id: int):
    """Get a collection with document count."""
    collection = await storage.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.put("/collections/{collection_id}", response_model=Collection)
async def update_collection(collection_id: int, data: CollectionUpdate):
    """Update a collection (admin)."""
    updates = data.model_dump(exclude_unset=True)
    collection = await storage.update_collection(collection_id, updates)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return collection


@router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: int, request: Request):
    """Delete a collection (admin). Cannot delete default collection."""
    deleted = await storage.delete_collection(collection_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Cannot delete collection (may be default or not found)")
    ip = get_client_ip(request)
    await log_activity(ip, "document.collection.delete", f"Deleted collection {collection_id}")
    return {"status": "deleted"}


# Document endpoints
@router.get("/collections/{collection_id}/documents", response_model=list[Document])
async def list_documents(collection_id: int):
    """List all documents in a collection."""
    collection = await storage.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    return await storage.list_documents(collection_id)


@router.post("/collections/{collection_id}/documents", response_model=Document)
async def upload_document(
    collection_id: int,
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...)
):
    """Upload a PDF document to a collection."""
    collection = await storage.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()
    content_hash = hashlib.md5(content).hexdigest()
    file_size = len(content)

    filename = f"{uuid.uuid4().hex}.pdf"
    file_path = UPLOAD_DIR / filename

    with open(file_path, "wb") as f:
        f.write(content)

    client_ip = request.client.host if request.client else None

    document = await storage.create_document(
        collection_id=collection_id,
        filename=filename,
        original_filename=file.filename,
        content_hash=content_hash,
        file_size=file_size,
        uploaded_by=client_ip
    )

    background_tasks.add_task(
        graphrag_service.process_document,
        document.id,
        file_path
    )

    ip = get_client_ip(request)
    await log_activity(ip, "document.upload", f"Uploaded '{file.filename}' to collection {collection_id}")
    return document


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(document_id: int):
    """Get document processing status."""
    doc = await storage.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentStatusResponse(
        id=doc.id,
        status=doc.status,
        error_message=doc.error_message,
        page_count=doc.page_count
    )


@router.get("/documents/{document_id}/file")
async def get_document_file(document_id: int):
    """Serve the PDF file for viewing."""
    doc = await storage.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = UPLOAD_DIR / doc.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=doc.original_filename
    )


@router.delete("/documents/{document_id}")
async def delete_document(document_id: int, request: Request):
    """Delete a document."""
    doc = await storage.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = UPLOAD_DIR / doc.filename
    if file_path.exists():
        file_path.unlink()

    deleted = await storage.delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete document")

    ip = get_client_ip(request)
    await log_activity(ip, "document.delete", f"Deleted document '{doc.original_filename}'")
    return {"status": "deleted"}


# Query endpoint
@router.post("/collections/{collection_id}/query")
async def query_collection(collection_id: int, data: DocumentQuery, request: Request):
    """Query a collection with GraphRAG streaming."""
    collection = await storage.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    ip = get_client_ip(request)
    await log_activity(ip, "document.query", f"Queried collection {collection_id}")

    async def generate():
        async for chunk in graphrag_service.query(collection_id, data.question, data.top_k):
            import json
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
