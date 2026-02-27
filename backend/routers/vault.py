"""API routes for the Vault (case records management)."""

import json
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

from backend.models import (
    VaultCase,
    VaultCaseCreate,
    VaultCaseUpdate,
    VaultCaseWithRecords,
    VaultRecord,
)
from backend.services import storage

router = APIRouter(prefix="/vault", tags=["vault"])

VAULT_DIR = Path("data/vault")
VAULT_DIR.mkdir(parents=True, exist_ok=True)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


# Case endpoints
@router.get("/cases", response_model=list[VaultCase])
async def list_cases(request: Request):
    """List cases accessible to the current user."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)
    return await storage.list_vault_cases(user_id)


@router.post("/cases", response_model=VaultCase)
async def create_case(data: VaultCaseCreate, request: Request):
    """Create a new vault case."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)
    return await storage.create_vault_case(
        user_id=user_id,
        identifier=data.identifier,
        name=data.name,
        description=data.description,
        is_public=data.is_public,
    )


@router.get("/cases/search", response_model=list[VaultCase])
async def search_cases(q: str, request: Request):
    """Search cases by name/identifier for @mention autocomplete."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)
    return await storage.search_vault_cases(user_id, q)


@router.get("/cases/{case_id}", response_model=VaultCaseWithRecords)
async def get_case(case_id: int, request: Request):
    """Get a case with all its records."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)
    case = await storage.get_vault_case(case_id, user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.put("/cases/{case_id}", response_model=VaultCase)
async def update_case(case_id: int, data: VaultCaseUpdate, request: Request):
    """Update a case (owner only)."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)
    updates = data.model_dump(exclude_unset=True)
    case = await storage.update_vault_case(case_id, user_id, updates)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not owner")
    return case


@router.delete("/cases/{case_id}")
async def delete_case(case_id: int, request: Request):
    """Delete a case and all records (owner only)."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)

    # Get case to clean up files
    case = await storage.get_vault_case(case_id, user_id)
    if case:
        for record in case.records:
            if record.filename:
                file_path = VAULT_DIR / record.filename
                if file_path.exists():
                    file_path.unlink()

    deleted = await storage.delete_vault_case(case_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Case not found or not owner")
    return {"status": "deleted"}


# Record endpoints
@router.post("/cases/{case_id}/records", response_model=VaultRecord)
async def add_record(
    case_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    record_type: str = Form("text"),
    title: str = Form(""),
    content: str = Form(None),
    record_date: str = Form(...),
    file: UploadFile | None = File(None),
):
    """Add a record to a case. Supports multipart form for file upload."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)

    # Verify case access
    case = await storage.get_vault_case(case_id, user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # Only owner can add records
    if case.user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the case owner can add records")

    filename = None
    original_filename = None
    file_size = None

    if record_type in ("document", "image") and file:
        file_content = await file.read()
        file_size = len(file_content)
        ext = Path(file.filename).suffix if file.filename else ""
        filename = f"{uuid.uuid4().hex}{ext}"
        file_path = VAULT_DIR / filename
        with open(file_path, "wb") as f:
            f.write(file_content)
        original_filename = file.filename

    record = await storage.create_vault_record(
        case_id=case_id,
        record_type=record_type,
        title=title,
        record_date=record_date,
        content=content,
        filename=filename,
        original_filename=original_filename,
        file_size=file_size,
    )

    # Generate AI description for documents/images in background
    if record_type in ("document", "image") and filename:
        background_tasks.add_task(
            generate_ai_description,
            record.id,
            record_type,
            VAULT_DIR / filename,
            original_filename,
        )

    return record


@router.put("/records/{record_id}/star", response_model=VaultRecord)
async def toggle_star(record_id: int, request: Request):
    """Toggle starred status on a record."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)

    # Verify access via the record's case
    record = await storage.get_vault_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    case = await storage.get_vault_case(record.case_id, user_id)
    if not case or case.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    updated = await storage.toggle_vault_record_star(record_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Record not found")
    return updated


@router.delete("/records/{record_id}")
async def delete_record(record_id: int, request: Request):
    """Delete a vault record."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)

    record = await storage.get_vault_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    case = await storage.get_vault_case(record.case_id, user_id)
    if not case or case.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Clean up file
    if record.filename:
        file_path = VAULT_DIR / record.filename
        if file_path.exists():
            file_path.unlink()

    deleted = await storage.delete_vault_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "deleted"}


@router.get("/records/{record_id}/file")
async def get_record_file(record_id: int, request: Request):
    """Download a record's attached file."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)

    record = await storage.get_vault_record(record_id)
    if not record or not record.filename:
        raise HTTPException(status_code=404, detail="File not found")

    case = await storage.get_vault_case(record.case_id, user_id)
    if not case:
        raise HTTPException(status_code=403, detail="Not authorized")

    file_path = VAULT_DIR / record.filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    from fastapi.responses import FileResponse
    return FileResponse(
        file_path,
        filename=record.original_filename or record.filename,
    )


# Record search
@router.get("/records/search")
async def search_records(q: str, request: Request, case_id: int | None = None):
    """Full-text search across vault records."""
    ip = get_client_ip(request)
    user_id = await storage.get_or_create_user(ip)
    results = await storage.search_vault_records(user_id, q, case_id)
    return results


async def generate_ai_description(
    record_id: int,
    record_type: str,
    file_path: Path,
    original_filename: str | None,
):
    """Background task: generate AI description for document/image records."""
    try:
        admin_settings = await storage.get_admin_settings()

        # Use dedicated vault server settings for each record type
        if record_type == "image":
            server_id = admin_settings.vault_image_server_id
        else:
            server_id = admin_settings.vault_text_server_id
        if not server_id:
            return

        server = await storage.get_server(server_id)
        if not server or not server.active:
            return

        if record_type == "document" and file_path.suffix.lower() == ".pdf":
            # Extract text from PDF
            text = await _extract_pdf_text(file_path)
            if not text:
                return
            # Truncate for LLM
            text = text[:8000]
            prompt = f"Summarize the following document concisely:\n\n{text}"
            messages = [{"role": "user", "content": prompt}]

        elif record_type == "image":
            import base64
            with open(file_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode()

            mime = "image/png"
            suffix = file_path.suffix.lower()
            if suffix in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif suffix == ".gif":
                mime = "image/gif"
            elif suffix == ".webp":
                mime = "image/webp"

            messages = [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_data}"}},
                    {"type": "text", "text": "Describe this image in detail. What does it contain?"},
                ],
            }]
        else:
            return

        # Call LLM
        payload = {
            "messages": messages,
            "stream": False,
            "temperature": 0.3,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{server.url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code == 200:
                data = response.json()
                if "choices" in data and data["choices"]:
                    description = data["choices"][0]["message"]["content"]
                    await storage.update_vault_record_ai_description(record_id, description)

    except Exception as e:
        # Log but don't fail - AI description is optional
        import logging
        logging.getLogger(__name__).warning(f"Failed to generate AI description for record {record_id}: {e}")


async def _extract_pdf_text(file_path: Path) -> str:
    """Extract text from a PDF file."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(file_path))
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text.strip()
    except ImportError:
        return ""
    except Exception:
        return ""
