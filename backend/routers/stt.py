"""STT API router for speech-to-text transcription."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.services.stt_service import stt_service


router = APIRouter(prefix="/stt", tags=["stt"])


@router.post("")
async def transcribe_audio(
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

    return result


@router.get("/models")
async def get_models():
    """Get list of available Whisper model names."""
    return {"models": stt_service.AVAILABLE_MODELS}
