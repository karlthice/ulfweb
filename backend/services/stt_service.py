"""Speech-to-text service using faster-whisper."""

import io
import tempfile
import time
from typing import Optional

from backend.services.storage import get_admin_settings


class STTService:
    """Service for speech-to-text transcription using faster-whisper."""

    AVAILABLE_MODELS = [
        "tiny",
        "base",
        "small",
        "medium",
        "large-v3",
        "large-v3-turbo",
    ]

    def __init__(self):
        self._model = None
        self._current_model_name: str | None = None

    def _get_model(self, model_name: str):
        """Get or load a Whisper model (lazy loading)."""
        if self._model is not None and self._current_model_name == model_name:
            return self._model

        from faster_whisper import WhisperModel

        print(f"Loading Whisper model: {model_name}")
        self._model = WhisperModel(model_name, device="auto", compute_type="default")
        self._current_model_name = model_name
        print(f"Whisper model '{model_name}' loaded")
        return self._model

    async def transcribe(
        self, audio_bytes: bytes, language: Optional[str] = None
    ) -> dict:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio data (any format ffmpeg can decode)
            language: Optional language code (e.g. 'is', 'en'). Auto-detected if None.

        Returns:
            Dict with 'text', 'language', 'duration' keys
        """
        # Get model name from admin settings
        admin_settings = await get_admin_settings()
        model_name = admin_settings.whisper_model or "large-v3-turbo"

        model = self._get_model(model_name)

        # Write audio to temp file (faster-whisper needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()

            start_time = time.time()

            kwargs = {}
            if language:
                kwargs["language"] = language

            segments, info = model.transcribe(tmp.name, **kwargs)

            # Collect all segment texts
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            elapsed = time.time() - start_time

        full_text = "".join(text_parts).strip()

        return {
            "text": full_text,
            "language": info.language,
            "duration": round(elapsed, 2),
        }


# Global service instance
stt_service = STTService()
