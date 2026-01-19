"""Translation endpoint with SSE streaming using Tilde."""

import json
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.config import settings
from backend.models import TranslateRequest

router = APIRouter(prefix="/translate", tags=["translate"])

# Language code to name mapping
LANGUAGE_NAMES = {
    "af": "Afrikaans", "sq": "Albanian", "am": "Amharic", "ar": "Arabic",
    "hy": "Armenian", "az": "Azerbaijani", "eu": "Basque", "be": "Belarusian",
    "bn": "Bengali", "bs": "Bosnian", "bg": "Bulgarian", "ca": "Catalan",
    "zh": "Chinese", "hr": "Croatian", "cs": "Czech", "da": "Danish",
    "nl": "Dutch", "en": "English", "et": "Estonian", "fi": "Finnish",
    "fr": "French", "gl": "Galician", "ka": "Georgian", "de": "German",
    "el": "Greek", "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi",
    "hu": "Hungarian", "is": "Icelandic", "id": "Indonesian", "ga": "Irish",
    "it": "Italian", "ja": "Japanese", "kn": "Kannada", "kk": "Kazakh",
    "ko": "Korean", "lv": "Latvian", "lt": "Lithuanian", "mk": "Macedonian",
    "ms": "Malay", "ml": "Malayalam", "mt": "Maltese", "mr": "Marathi",
    "mn": "Mongolian", "ne": "Nepali", "no": "Norwegian", "fa": "Persian",
    "pl": "Polish", "pt": "Portuguese", "pa": "Punjabi", "ro": "Romanian",
    "ru": "Russian", "sr": "Serbian", "si": "Sinhala", "sk": "Slovak",
    "sl": "Slovenian", "es": "Spanish", "sw": "Swahili", "sv": "Swedish",
    "ta": "Tamil", "te": "Telugu", "th": "Thai", "tr": "Turkish",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese",
    "cy": "Welsh", "zu": "Zulu"
}


async def stream_translation(
    text: str,
    source_lang: str,
    target_lang: str
) -> AsyncGenerator[str, None]:
    """Stream translation response from Tilde server."""
    source_name = LANGUAGE_NAMES.get(source_lang, source_lang)
    target_name = LANGUAGE_NAMES.get(target_lang, target_lang)

    # Build prompt for translation - be specific to avoid extra commentary
    prompt = f"Translate this text from {source_name} to {target_name}. Only provide the translation, nothing else:\n\n{text}"

    # Build request payload in OpenAI chat format
    # Limit tokens to roughly 2x the input to avoid excessive output
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": max(256, len(text) * 3),
    }

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{settings.tilde.url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Translation server error: {error_text.decode()}'})}\n\n"
                    return

                # Buffer to detect special tokens that may be split across chunks
                token_buffer = ""
                stop_streaming = False

                async for line in response.aiter_lines():
                    if not line or stop_streaming:
                        continue

                    if line.startswith("data: "):
                        data = line[6:]

                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content", "")

                                if content:
                                    # Add to buffer to detect special tokens
                                    token_buffer += content

                                    # Check if buffer contains start of special token
                                    if "<|" in token_buffer:
                                        # Output everything before the special token
                                        idx = token_buffer.find("<|")
                                        if idx > 0:
                                            yield f"data: {json.dumps({'type': 'content', 'content': token_buffer[:idx]})}\n\n"
                                        stop_streaming = True
                                        continue

                                    # If buffer is getting long and no special token, flush it
                                    if len(token_buffer) > 10:
                                        # Keep last few chars in case token spans chunks
                                        to_send = token_buffer[:-5]
                                        token_buffer = token_buffer[-5:]
                                        if to_send:
                                            yield f"data: {json.dumps({'type': 'content', 'content': to_send})}\n\n"
                        except json.JSONDecodeError:
                            continue

                # Flush remaining buffer if no special token detected
                if token_buffer and not stop_streaming and "<|" not in token_buffer:
                    yield f"data: {json.dumps({'type': 'content', 'content': token_buffer})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except httpx.ConnectError:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Cannot connect to translation server. Is Tilde running?'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


@router.post("")
async def translate_text(data: TranslateRequest):
    """Translate text and stream the response."""
    return StreamingResponse(
        stream_translation(data.text, data.source_lang, data.target_lang),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
