"""TTS API router for text-to-speech synthesis."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.services.storage import log_activity
from backend.services.tts_service import tts_service


router = APIRouter(prefix="/tts", tags=["tts"])


class TTSRequest(BaseModel):
    """Request model for TTS synthesis."""

    text: str
    language: str | None = None


class TTSResponse(BaseModel):
    """Response model for TTS metadata."""

    detected_language: str
    available: bool


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.post("")
async def synthesize_speech(data: TTSRequest, request: Request) -> Response:
    """Synthesize text to speech.

    Returns WAV audio data.
    """
    if not data.text or not data.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    # Detect language if not provided
    language = data.language or tts_service.detect_language(data.text)

    # Synthesize
    audio_data = tts_service.synthesize(data.text, language)

    if audio_data is None:
        raise HTTPException(
            status_code=503,
            detail=f"TTS synthesis failed. Voice for '{language}' may not be available."
        )

    ip = get_client_ip(request)
    await log_activity(ip, "tts.synthesize", f"Synthesized speech ({language}, {len(data.text)} chars)")
    return Response(
        content=audio_data,
        media_type="audio/wav",
        headers={
            "X-TTS-Language": language,
            "Content-Disposition": "inline; filename=speech.wav"
        }
    )


@router.get("/voices")
async def get_voices() -> dict[str, str]:
    """Get list of available voices (languages with downloaded models)."""
    return tts_service.get_available_voices()


@router.get("/languages")
async def get_languages() -> dict[str, str]:
    """Get list of all supported languages."""
    return tts_service.get_supported_languages()


@router.post("/detect")
async def detect_language(data: TTSRequest) -> TTSResponse:
    """Detect language and check if voice is available."""
    if not data.text or not data.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    language = tts_service.detect_language(data.text)
    available_voices = tts_service.get_available_voices()

    return TTSResponse(
        detected_language=language,
        available=language in available_voices
    )
