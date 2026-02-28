"""API routes for the Vault (case records management)."""

import json
import uuid
from pathlib import Path

import httpx
from lingua import Language, LanguageDetectorBuilder
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile

from backend.auth import get_client_ip, require_user
from backend.models import (
    VaultCase,
    VaultCaseCreate,
    VaultCaseUpdate,
    VaultCaseWithRecords,
    VaultRecord,
    VaultRecordUpdate,
)
from backend.services import storage
from backend.services.storage import log_activity

router = APIRouter(prefix="/vault", tags=["vault"])

VAULT_DIR = Path("data/vault")
VAULT_DIR.mkdir(parents=True, exist_ok=True)

# Language detector for matching summary language to record language
_LANG_DETECTOR = (
    LanguageDetectorBuilder
    .from_languages(
        Language.ICELANDIC, Language.ENGLISH, Language.BOKMAL, Language.NYNORSK,
        Language.SWEDISH, Language.DANISH, Language.GERMAN, Language.FRENCH,
        Language.ITALIAN, Language.SPANISH,
    )
    .build()
)

_LINGUA_NAMES = {
    Language.ICELANDIC: "Icelandic", Language.ENGLISH: "English",
    Language.BOKMAL: "Norwegian", Language.NYNORSK: "Norwegian",
    Language.SWEDISH: "Swedish", Language.DANISH: "Danish",
    Language.GERMAN: "German", Language.FRENCH: "French",
    Language.ITALIAN: "Italian", Language.SPANISH: "Spanish",
}


# Case endpoints
@router.get("/cases", response_model=list[VaultCase])
async def list_cases(request: Request):
    """List cases accessible to the current user."""
    user = await require_user(request)
    return await storage.list_vault_cases(user["id"])


@router.post("/cases", response_model=VaultCase)
async def create_case(data: VaultCaseCreate, request: Request):
    """Create a new vault case."""
    user = await require_user(request)
    ip = get_client_ip(request)
    case = await storage.create_vault_case(
        user_id=user["id"],
        identifier=data.identifier,
        name=data.name,
        description=data.description,
        is_public=data.is_public,
        owner_ip=user["username"],
    )
    await log_activity(ip, "vault.case.create", f"Created case '{data.name}' ({data.identifier})", user["id"])
    return case


@router.get("/cases/search", response_model=list[VaultCase])
async def search_cases(q: str, request: Request):
    """Search cases by name/identifier for @mention autocomplete."""
    user = await require_user(request)
    return await storage.search_vault_cases(user["id"], q)


@router.get("/cases/{case_id}", response_model=VaultCaseWithRecords)
async def get_case(case_id: int, request: Request):
    """Get a case with all its records."""
    user = await require_user(request)
    case = await storage.get_vault_case(case_id, user["id"])
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case.current_user_id = user["id"]
    return case


@router.put("/cases/{case_id}", response_model=VaultCase)
async def update_case(case_id: int, data: VaultCaseUpdate, request: Request):
    """Update a case (owner only)."""
    user = await require_user(request)
    ip = get_client_ip(request)
    updates = data.model_dump(exclude_unset=True)
    case = await storage.update_vault_case(case_id, user["id"], updates)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found or not owner")
    await log_activity(ip, "vault.case.update", f"Updated case '{case.name}'", user["id"])
    return case


@router.delete("/cases/{case_id}")
async def delete_case(case_id: int, request: Request):
    """Delete a case and all records (owner only)."""
    user = await require_user(request)
    ip = get_client_ip(request)
    user_id = user["id"]

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
    await log_activity(ip, "vault.case.delete", f"Deleted case {case_id}", user_id)
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
    user = await require_user(request)
    ip = get_client_ip(request)
    user_id = user["id"]

    # Verify case access (any viewer can add records)
    case = await storage.get_vault_case(case_id, user_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

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
        created_by_user_id=user_id,
        created_by_ip=ip,
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

    # Generate case AI summary in background (regenerate from all records)
    background_tasks.add_task(generate_case_ai_summary, case_id)

    await log_activity(ip, "vault.record.add", f"Added {record_type} record to case {case_id}", user_id)
    return record


@router.put("/records/{record_id}/star", response_model=VaultRecord)
async def toggle_star(record_id: int, request: Request):
    """Toggle starred status on a record."""
    user = await require_user(request)
    user_id = user["id"]

    # Verify access via the record's case (any viewer can toggle stars)
    record = await storage.get_vault_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    case = await storage.get_vault_case(record.case_id, user_id)
    if not case:
        raise HTTPException(status_code=403, detail="Not authorized")

    updated = await storage.toggle_vault_record_star(record_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Record not found")
    return updated


@router.delete("/records/{record_id}")
async def delete_record(record_id: int, request: Request, background_tasks: BackgroundTasks):
    """Delete a vault record."""
    user = await require_user(request)
    ip = get_client_ip(request)
    user_id = user["id"]

    record = await storage.get_vault_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    case = await storage.get_vault_case(record.case_id, user_id)
    if not case:
        raise HTTPException(status_code=403, detail="Not authorized")
    # Allow case owner or record creator to delete
    if case.user_id != user_id and record.created_by_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the case owner or record creator can delete records")

    case_id = record.case_id

    # Clean up file
    if record.filename:
        file_path = VAULT_DIR / record.filename
        if file_path.exists():
            file_path.unlink()

    deleted = await storage.delete_vault_record(record_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Record not found")

    # Regenerate case AI summary after deletion
    background_tasks.add_task(generate_case_ai_summary, case_id)

    await log_activity(ip, "vault.record.delete", f"Deleted record {record_id} from case {case_id}", user_id)
    return {"status": "deleted"}


@router.put("/records/{record_id}", response_model=VaultRecord)
async def update_record(record_id: int, data: VaultRecordUpdate, request: Request):
    """Edit a text record (creator only, within 24 hours)."""
    from datetime import datetime, timedelta

    user = await require_user(request)
    ip = get_client_ip(request)
    user_id = user["id"]

    record = await storage.get_vault_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Verify user can view the case
    case = await storage.get_vault_case(record.case_id, user_id)
    if not case:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Only text records can be edited
    if record.record_type != "text":
        raise HTTPException(status_code=403, detail="Only text records can be edited")

    # Only the creator can edit
    if record.created_by_user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the record creator can edit")

    # Must be within 24 hours of creation
    age = datetime.utcnow() - record.created_at
    if age > timedelta(hours=24):
        raise HTTPException(status_code=403, detail="Records can only be edited within 24 hours of creation")

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return record

    updated = await storage.update_vault_record(record_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Record not found")
    await log_activity(ip, "vault.record.update", f"Updated record {record_id}", user_id)
    return updated


@router.get("/records/{record_id}/file")
async def get_record_file(record_id: int, request: Request):
    """Download a record's attached file."""
    user = await require_user(request)
    user_id = user["id"]

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
    user = await require_user(request)
    ip = get_client_ip(request)
    results = await storage.search_vault_records(user["id"], q, case_id)
    await log_activity(ip, "vault.search", f"Searched vault for '{q}'", user["id"])
    return results


async def generate_case_ai_summary(case_id: int):
    """Background task: generate AI summary for a case from all its records."""
    try:
        from backend.database import get_db

        # Fetch case info and all records
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT name, identifier, description FROM vault_cases WHERE id = ?",
                (case_id,)
            )
            case_row = await cursor.fetchone()
            if not case_row:
                return

            case_info = dict(case_row)
            case_label = f"'{case_info['name']}' ({case_info['identifier']})"

            cursor = await db.execute(
                """SELECT record_type, title, content, ai_description, record_date
                   FROM vault_records
                   WHERE case_id = ?
                   ORDER BY record_date ASC, created_at ASC""",
                (case_id,)
            )
            records = [dict(r) for r in await cursor.fetchall()]

        # If no records, clear the summary
        if not records:
            await storage.update_vault_case_ai_summary(case_id, "")
            return

        admin_settings = await storage.get_admin_settings()
        server_id = admin_settings.vault_text_server_id
        if not server_id:
            await log_activity("system", "vault.summary.skip", f"No text server configured, skipped summary for case {case_label}")
            return

        server = await storage.get_server(server_id)
        if not server or not server.active:
            await log_activity("system", "vault.summary.skip", f"Text server not available, skipped summary for case {case_label}")
            return

        # Build record context
        record_lines = []
        all_text = []
        for r in records:
            if r["record_type"] == "text":
                snippet = (r["content"] or "")[:300]
            else:
                snippet = (r["ai_description"] or "No description available")[:300]
            record_lines.append(
                f"- [{r['record_date']}] {r['title'] or 'Untitled'} ({r['record_type']}): {snippet}"
            )
            all_text.append(snippet)

        # Detect record language so the summary matches
        sample_text = " ".join(all_text)[:2000]
        detected = _LANG_DETECTOR.detect_language_of(sample_text)
        lang_name = _LINGUA_NAMES.get(detected, "English") if detected else "English"
        lang_instruction = f" Write the summary in {lang_name}." if lang_name != "English" else ""

        prompt = (
            f"Write a brief factual summary of this case. State only what the records say — "
            f"no interpretation, no speculation, no filler. Use short sentences. "
            f"List key dates and facts. 150 words maximum.{lang_instruction}\n\n"
            f"Case: {case_info['name']} ({case_info['identifier']})\n"
            f"Description: {case_info['description'] or 'N/A'}\n\n"
            f"Records (chronological):\n" + "\n".join(record_lines)
        )

        payload = {
            "messages": [{"role": "user", "content": prompt}],
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
                    summary = data["choices"][0]["message"]["content"]
                    summary = _clean_llm_output(summary)
                    await storage.update_vault_case_ai_summary(case_id, summary)
                    await log_activity("system", "vault.summary.ok", f"Generated summary for case {case_label} ({len(records)} records)")
                    return

            await log_activity("system", "vault.summary.fail", f"LLM returned status {response.status_code} for case {case_label}")

    except Exception as e:
        await log_activity("system", "vault.summary.fail", f"Failed to generate summary for case {case_id}: {e}")


async def generate_ai_description(
    record_id: int,
    record_type: str,
    file_path: Path,
    original_filename: str | None,
):
    """Background task: generate AI description for document/image records."""
    file_label = original_filename or f"record {record_id}"
    try:
        admin_settings = await storage.get_admin_settings()

        # Use dedicated vault server settings for each record type
        if record_type == "image":
            server_id = admin_settings.vault_image_server_id
        else:
            server_id = admin_settings.vault_text_server_id
        if not server_id:
            await log_activity("system", "vault.description.skip", f"No {record_type} server configured, skipped description for '{file_label}'")
            return

        server = await storage.get_server(server_id)
        if not server or not server.active:
            await log_activity("system", "vault.description.skip", f"Server not available, skipped description for '{file_label}'")
            return

        if record_type == "document" and file_path.suffix.lower() == ".pdf":
            # Extract text from PDF
            text = await _extract_pdf_text(file_path)
            if not text:
                await log_activity("system", "vault.description.fail", f"Could not extract text from '{file_label}'")
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
                    description = _clean_llm_output(description)
                    await storage.update_vault_record_ai_description(record_id, description)
                    await log_activity("system", "vault.description.ok", f"Generated description for '{file_label}'")
                    return

            await log_activity("system", "vault.description.fail", f"LLM returned status {response.status_code} for '{file_label}'")

    except Exception as e:
        await log_activity("system", "vault.description.fail", f"Failed to generate description for '{file_label}': {e}")


import re

def _clean_llm_output(text: str) -> str:
    """Strip thinking tags and duplicated content from LLM output."""
    # Remove <think>...</think> blocks (reasoning models)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Remove stray closing </think> tags
    text = re.sub(r"</think>\s*", "", text)
    # Remove (Word count: N) artifacts
    text = re.sub(r"\(Word count:\s*\d+\)\s*", "", text)
    return text.strip()


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
