"""Translation endpoint with SSE streaming using Tilde."""

import json
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.auth import get_client_ip, require_user
from backend.config import settings
from backend.models import TranslateRequest
from backend.services.storage import get_admin_settings, get_server, log_activity

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
    """Stream translation response from configured translation server."""
    # Resolve translation server URL: admin setting > config fallback
    server_url = settings.tilde.url
    try:
        admin_settings = await get_admin_settings()
        if admin_settings.translation_server_id:
            server = await get_server(admin_settings.translation_server_id)
            if server:
                server_url = server.url
    except Exception:
        pass  # Fall back to config

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
        "reasoning_budget": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{server_url}/v1/chat/completions",
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
                in_think = False  # Track <think>...</think> blocks

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

                                    # Strip <think>...</think> blocks (reasoning models)
                                    while "<think>" in token_buffer:
                                        before = token_buffer[:token_buffer.find("<think>")]
                                        after = token_buffer[token_buffer.find("<think>") + 7:]
                                        if "</think>" in after:
                                            token_buffer = before + after[after.find("</think>") + 8:]
                                        else:
                                            # Still inside think block - send what's before it
                                            if before:
                                                yield f"data: {json.dumps({'type': 'content', 'content': before})}\n\n"
                                            token_buffer = after
                                            in_think = True
                                            break

                                    # If inside a think block, look for closing tag
                                    if in_think:
                                        if "</think>" in token_buffer:
                                            token_buffer = token_buffer[token_buffer.find("</think>") + 8:]
                                            in_think = False
                                        else:
                                            # Discard buffered think content, keep tail for partial tag
                                            token_buffer = token_buffer[-8:] if len(token_buffer) > 8 else token_buffer
                                            continue

                                    # Strip stray </think> tags
                                    token_buffer = token_buffer.replace("</think>", "")

                                    if in_think:
                                        continue

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
                if token_buffer and not stop_streaming and not in_think and "<|" not in token_buffer:
                    yield f"data: {json.dumps({'type': 'content', 'content': token_buffer})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except httpx.ConnectError:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Cannot connect to translation server. Is Tilde running?'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


@router.post("")
async def translate_text(data: TranslateRequest, request: Request):
    """Translate text and stream the response."""
    await require_user(request)
    ip = get_client_ip(request)
    source_name = LANGUAGE_NAMES.get(data.source_lang, data.source_lang)
    target_name = LANGUAGE_NAMES.get(data.target_lang, data.target_lang)
    await log_activity(ip, "translate", f"Translated from {source_name} to {target_name}")
    return StreamingResponse(
        stream_translation(data.text, data.source_lang, data.target_lang),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
