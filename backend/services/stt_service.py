"""Speech-to-text service using faster-whisper."""

import os
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

    # Punctuated prompts per language to condition Whisper output style
    PUNCTUATION_PROMPTS = {
        "is": "Halló, hvernig hefur þú það? Já, mér líður vel. Við skulum byrja.",
        "en": "Hello, how are you? Yes, I'm doing well. Let's get started.",
        "no": "Hei, hvordan har du det? Ja, jeg har det bra. La oss begynne.",
        "sv": "Hej, hur mår du? Ja, jag mår bra. Låt oss börja.",
        "da": "Hej, hvordan har du det? Ja, jeg har det godt. Lad os komme i gang.",
        "de": "Hallo, wie geht es Ihnen? Ja, mir geht es gut. Fangen wir an.",
        "fr": "Bonjour, comment allez-vous ? Oui, je vais bien. Commençons.",
        "es": "Hola, ¿cómo estás? Sí, estoy bien. Empecemos.",
        "it": "Ciao, come stai? Sì, sto bene. Cominciamo.",
    }

    def __init__(self):
        self._model = None
        self._current_model_name: str | None = None
        self._device: str = "cpu"

    @property
    def model_loaded(self) -> bool:
        """Whether a Whisper model is currently loaded in memory."""
        return self._model is not None

    def _get_model(self, model_name: str):
        """Get or load a Whisper model (lazy loading)."""
        if self._model is not None and self._current_model_name == model_name:
            return self._model

        from faster_whisper import WhisperModel
        import ctranslate2

        # Pick optimal settings based on available hardware
        # Try CUDA first, fall back to CPU if driver is incompatible
        device = "cpu"
        compute_type = "int8"
        extra = {"cpu_threads": os.cpu_count() // 2 or 4}

        try:
            ctranslate2.get_supported_compute_types("cuda")
            # Verify CUDA actually works by loading on it
            device = "cuda"
            compute_type = "float16"
            extra = {}
            print(f"Loading Whisper model: {model_name} (CUDA, float16)")
            self._model = WhisperModel(
                model_name, device=device, compute_type=compute_type,
            )
        except (RuntimeError, Exception) as e:
            if device == "cuda":
                print(f"CUDA failed ({e}), falling back to CPU")
            device = "cpu"
            compute_type = "int8"
            extra = {"cpu_threads": os.cpu_count() // 2 or 4}
            print(f"Loading Whisper model: {model_name} (CPU, int8, {extra['cpu_threads']} threads)")
            self._model = WhisperModel(
                model_name, device=device, compute_type=compute_type,
                **extra,
            )

        self._current_model_name = model_name
        self._device = device
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

            prompt = self.PUNCTUATION_PROMPTS.get(language, self.PUNCTUATION_PROMPTS["en"])

            segments, info = model.transcribe(
                wav.name,
                beam_size=5 if self._device == "cuda" else 1,
                vad_filter=True,
                initial_prompt=prompt,
                **kwargs,
            )

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

            prompt = self.PUNCTUATION_PROMPTS.get(language, self.PUNCTUATION_PROMPTS["en"])

            segments, info = model.transcribe(
                tmp.name,
                beam_size=5 if self._device == "cuda" else 1,
                vad_filter=True,
                initial_prompt=prompt,
                **kwargs,
            )
            text_parts = [seg.text for seg in segments]

        return "".join(text_parts).strip()


# Global service instance
stt_service = STTService()
