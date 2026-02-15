"""Text-to-speech service using Piper TTS."""

import io
import wave
from pathlib import Path
from typing import Optional

from lingua import Language, LanguageDetectorBuilder
from piper import PiperVoice

from backend.config import settings


class TTSService:
    """Service for text-to-speech synthesis using Piper TTS."""

    # Supported languages with their display names
    SUPPORTED_LANGUAGES = {
        "is": "Icelandic",
        "en": "English",
        "no": "Norwegian",
        "sv": "Swedish",
        "da": "Danish",
        "de": "German",
        "fr": "French",
        "it": "Italian",
        "es": "Spanish",
    }

    # Map lingua Language enum to our language codes
    LINGUA_MAP = {
        Language.ICELANDIC: "is",
        Language.ENGLISH: "en",
        Language.BOKMAL: "no",
        Language.NYNORSK: "no",
        Language.SWEDISH: "sv",
        Language.DANISH: "da",
        Language.GERMAN: "de",
        Language.FRENCH: "fr",
        Language.ITALIAN: "it",
        Language.SPANISH: "es",
    }

    def __init__(self):
        self._voices: dict[str, PiperVoice] = {}
        self._voices_path = Path(settings.tts.voices_path)
        self._voice_mapping = settings.tts.voice_mapping

        # Build language detector for supported languages only
        self._detector = (
            LanguageDetectorBuilder
            .from_languages(*self.LINGUA_MAP.keys())
            .build()
        )

    def _get_voice(self, language: str) -> Optional[PiperVoice]:
        """Get or load a voice for the specified language."""
        if language not in self._voice_mapping:
            return None

        if language not in self._voices:
            voice_name = self._voice_mapping[language]
            model_path = self._voices_path / f"{voice_name}.onnx"
            config_path = self._voices_path / f"{voice_name}.onnx.json"

            if not model_path.exists():
                return None

            try:
                self._voices[language] = PiperVoice.load(
                    str(model_path),
                    config_path=str(config_path) if config_path.exists() else None
                )
            except Exception as e:
                print(f"Failed to load voice for {language}: {e}")
                return None

        return self._voices[language]

    def detect_language(self, text: str) -> str:
        """Detect the language of the text.

        Returns the detected language code if supported, otherwise 'en'.
        """
        if not text or not text.strip():
            return "en"

        detected = self._detector.detect_language_of(text)
        if detected and detected in self.LINGUA_MAP:
            return self.LINGUA_MAP[detected]

        return "en"  # Default to English

    def get_available_voices(self) -> dict[str, str]:
        """Get list of available voices (languages with downloaded models)."""
        available = {}
        for lang_code, lang_name in self.SUPPORTED_LANGUAGES.items():
            voice_name = self._voice_mapping.get(lang_code)
            if voice_name:
                model_path = self._voices_path / f"{voice_name}.onnx"
                if model_path.exists():
                    available[lang_code] = lang_name
        return available

    def get_supported_languages(self) -> dict[str, str]:
        """Get all supported languages (whether or not voices are downloaded)."""
        return self.SUPPORTED_LANGUAGES.copy()

    def synthesize(self, text: str, language: Optional[str] = None) -> Optional[bytes]:
        """Synthesize text to speech.

        Args:
            text: The text to synthesize
            language: Language code (auto-detected if not provided)

        Returns:
            WAV audio bytes, or None if synthesis failed
        """
        if not text or not text.strip():
            return None

        # Detect language if not specified
        if not language:
            language = self.detect_language(text)

        voice = self._get_voice(language)
        if not voice:
            # Fall back to English if requested language not available
            if language != "en":
                voice = self._get_voice("en")
            if not voice:
                return None

        try:
            # Create WAV in memory
            audio_buffer = io.BytesIO()

            with wave.open(audio_buffer, "wb") as wav_file:
                # synthesize_wav sets the WAV format automatically
                voice.synthesize_wav(text, wav_file)

            return audio_buffer.getvalue()
        except Exception as e:
            print(f"TTS synthesis error: {e}")
            return None


# Global service instance
tts_service = TTSService()
