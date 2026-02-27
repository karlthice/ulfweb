"""STT API router for speech-to-text transcription."""

import asyncio
import json
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from backend.services.meeting_session import meeting_session_manager
from backend.services.stt_service import stt_service
from backend.services.storage import get_admin_settings, log_activity


router = APIRouter(prefix="/stt", tags=["stt"])


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.post("")
async def transcribe_audio(
    request: Request,
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
):
    """Transcribe uploaded audio to text.

    Accepts audio file (webm, wav, mp3, etc.) and returns transcription.
    """
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="No audio data provided")

    try:
        result = await stt_service.transcribe(audio_bytes, language=language or None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    ip = get_client_ip(request)
    await log_activity(ip, "stt.transcribe", f"Transcribed audio ({len(audio_bytes)} bytes)")
    return result


@router.get("/status")
async def get_status():
    """Check whether the Whisper model is loaded."""
    return {"model_loaded": stt_service.model_loaded}


@router.get("/models")
async def get_models():
    """Get list of available Whisper model names."""
    return {"models": stt_service.AVAILABLE_MODELS}


# --- Meeting dictation endpoints ---

@router.post("/meeting/start")
async def meeting_start(request: Request):
    """Create a new meeting recording session."""
    session_id = meeting_session_manager.create_session()
    ip = get_client_ip(request)
    await log_activity(ip, "stt.meeting.start", f"Started meeting session {session_id}")
    return {"session_id": session_id}


@router.post("/meeting/{session_id}/chunk")
async def meeting_chunk(
    session_id: str,
    audio: UploadFile = File(...),
    chunk_index: int = Form(...),
):
    """Upload an audio chunk for a meeting session."""
    if not meeting_session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    chunk_data = await audio.read()
    if not chunk_data:
        raise HTTPException(status_code=400, detail="Empty chunk")

    meeting_session_manager.add_chunk(session_id, chunk_data, chunk_index)
    return {"status": "ok", "chunk_index": chunk_index}


@router.post("/meeting/{session_id}/finalize")
async def meeting_finalize(
    session_id: str,
    request: Request,
    language: str | None = Form(default=None),
):
    """Finalize a meeting session: assemble, diarize, and transcribe.

    Returns an SSE stream with progress events and the final transcript.
    """
    if not meeting_session_manager.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    ip = get_client_ip(request)
    await log_activity(ip, "stt.meeting.finalize", f"Finalized meeting session {session_id}")

    language = language or None

    async def event_stream():
        loop = asyncio.get_event_loop()
        try:
            # Step 1: Assemble chunks
            yield _sse("progress", {"stage": "assembling", "message": "Assembling audio chunks..."})
            wav_path = await loop.run_in_executor(
                None, meeting_session_manager.assemble_chunks, session_id
            )

            # Step 2: Diarize
            yield _sse("progress", {"stage": "diarizing", "message": "Identifying speakers..."})
            from backend.services.diarization_service import diarization_service
            segments = await loop.run_in_executor(
                None, diarization_service.diarize, wav_path
            )

            if not segments:
                yield _sse("error", {"message": "No speech segments detected"})
                return

            num_speakers = len(set(s["speaker"] for s in segments))
            yield _sse("progress", {
                "stage": "transcribing",
                "message": f"Transcribing... (0/{len(segments)} segments)",
                "total_segments": len(segments),
                "num_speakers": num_speakers,
            })

            # Step 3: Get whisper model name
            admin_settings = await get_admin_settings()
            model_name = admin_settings.whisper_model or "large-v3-turbo"

            # Step 4: Transcribe each segment
            transcript_lines = []
            start_time = time.time()

            for i, seg in enumerate(segments):
                text = await loop.run_in_executor(
                    None,
                    stt_service.transcribe_file_segment,
                    wav_path, seg["start"], seg["end"],
                    model_name, language,
                )

                if text:
                    line = f"Speaker {seg['speaker']}: {text}"
                    transcript_lines.append(line)
                    yield _sse("transcript_line", {
                        "line": line,
                        "index": i,
                        "speaker": seg["speaker"],
                        "start": seg["start"],
                        "end": seg["end"],
                    })

                yield _sse("progress", {
                    "stage": "transcribing",
                    "message": f"Transcribing... ({i + 1}/{len(segments)} segments)",
                    "completed_segments": i + 1,
                    "total_segments": len(segments),
                })

            elapsed = time.time() - start_time
            full_transcript = "\n\n".join(transcript_lines)

            yield _sse("done", {
                "transcript": full_transcript,
                "num_speakers": num_speakers,
                "num_segments": len(segments),
                "duration": round(elapsed, 2),
            })

        except Exception as e:
            yield _sse("error", {"message": str(e)})
        finally:
            meeting_session_manager.cleanup_session(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    """Format a server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
