"""Speech-to-text service using faster-whisper."""

import subprocess
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
        "language-and-voice-lab/whisper-large-icelandic-62640-steps-967h-ct2",
    ]

    def __init__(self):
        self._model = None
        self._current_model_name: str | None = None

    @property
    def model_loaded(self) -> bool:
        """Whether a Whisper model is currently loaded in memory."""
        return self._model is not None

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

        # Write audio to temp file, then convert to WAV for reliable decoding.
        # WebM files from MediaRecorder often lack proper duration/seek metadata,
        # which can cause Whisper to only decode the tail end of longer recordings.
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as raw, \
             tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as wav:
            raw.write(audio_bytes)
            raw.flush()

            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", raw.name,
                    "-ar", "16000",
                    "-ac", "1",
                    "-f", "wav",
                    wav.name,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg conversion failed: {result.stderr}")

            start_time = time.time()

            kwargs = {}
            if language:
                kwargs["language"] = language

            segments, info = model.transcribe(wav.name, **kwargs)

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

    def transcribe_file_segment(
        self, wav_path: str, start: float, end: float,
        model_name: str, language: Optional[str] = None,
    ) -> str:
        """Transcribe a time range from a WAV file (synchronous).

        Uses ffmpeg to extract the segment, then transcribes with faster-whisper.

        Returns the transcribed text, or empty string for very short segments.
        """
        duration = end - start
        if duration < 0.5:
            return ""

        model = self._get_model(model_name)

        # Extract segment to temp file using ffmpeg
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", wav_path,
                    "-ss", str(start),
                    "-to", str(end),
                    "-ar", "16000",
                    "-ac", "1",
                    "-f", "wav",
                    tmp.name,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return ""

            kwargs = {}
            if language:
                kwargs["language"] = language

            segments, info = model.transcribe(tmp.name, **kwargs)
            text_parts = [seg.text for seg in segments]

        return "".join(text_parts).strip()


# Global service instance
stt_service = STTService()
