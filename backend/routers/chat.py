"""Chat endpoint with SSE streaming."""

import json
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.auth import get_client_ip, require_user
from backend.config import settings
from backend.models import ChatRequest
from backend.services.storage import (
    add_message,
    get_admin_settings,
    get_conversation,
    get_conversation_messages,
    get_server,
    get_user_settings,
    get_vault_case_context,
    list_servers,
    log_activity,
    touch_conversation,
    update_conversation,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _estimate_tokens(text: str) -> int:
    """Rough character-based token estimate (~4 chars per token)."""
    return len(text) // 4 + 1


async def stream_chat_response(
    conversation_id: int,
    user_id: int,
    user_message: str,
    image_base64: str | None = None,
    case_refs: list[int] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat response from llama.cpp server."""
    # Save user message
    await add_message(conversation_id, "user", user_message)

    # Get conversation messages and user settings
    messages = await get_conversation_messages(conversation_id)
    user_settings = await get_user_settings(user_id)

    # Resolve server early so we can use ctx_size for the token budget
    server_url = settings.llama.url
    server_name = server_url
    ctx_budget = 32768  # fallback
    admin_cfg = await get_admin_settings()
    if admin_cfg.chat_server_id:
        server = await get_server(admin_cfg.chat_server_id)
        if server and server.active:
            server_url = server.url
            server_name = server.friendly_name
            ctx_budget = server.ctx_size
        else:
            active_servers = await list_servers(active_only=True)
            if active_servers:
                server_url = active_servers[0].url
                server_name = active_servers[0].friendly_name
                ctx_budget = active_servers[0].ctx_size
    else:
        active_servers = await list_servers(active_only=True)
        if active_servers:
            server_url = active_servers[0].url
            server_name = active_servers[0].friendly_name
            ctx_budget = active_servers[0].ctx_size

    # Build messages for llama.cpp API
    llama_messages = []

    # Build system prompt, merging vault case context if @Case references present
    system_parts = []
    if user_settings.system_prompt:
        system_parts.append(user_settings.system_prompt)

    if case_refs:
        vault_chat_records = admin_cfg.vault_chat_records
        for case_id in case_refs:
            ctx = await get_vault_case_context(case_id, user_id, max_recent=vault_chat_records)
            if ctx:
                system_parts.append(ctx)

    if system_parts:
        llama_messages.append({
            "role": "system",
            "content": "\n\n".join(system_parts)
        })

    # Sliding window: fit recent history within the server's context budget
    # Reserve tokens for the response and fixed parts (system prompt + current message)
    used_tokens = user_settings.max_tokens  # reserve for response
    if system_parts:
        used_tokens += _estimate_tokens("\n\n".join(system_parts))
    used_tokens += _estimate_tokens(user_message)

    remaining = ctx_budget - used_tokens
    context_overflow = used_tokens > ctx_budget

    # Walk history newest-first (excluding current user message), add what fits
    history = messages[:-1]  # Exclude last message (it's the current user message)
    window = []
    for msg in reversed(history):
        msg_tokens = _estimate_tokens(msg.content)
        if msg_tokens > remaining:
            break
        remaining -= msg_tokens
        window.append({"role": msg.role, "content": msg.content})
    window.reverse()
    llama_messages.extend(window)

    # Add the current user message (with image if present)
    if image_base64:
        # Multimodal format for vision models
        llama_messages.append({
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_base64}},
                {"type": "text", "text": user_message}
            ]
        })
    else:
        llama_messages.append({
            "role": "user",
            "content": user_message
        })

    # Build request payload
    payload = {
        "messages": llama_messages,
        "stream": True,
        "temperature": user_settings.temperature,
        "top_k": user_settings.top_k,
        "top_p": user_settings.top_p,
        "max_tokens": user_settings.max_tokens,
    }

    # Backend-specific parameters
    if admin_cfg.llm_backend == "vllm":
        payload["repetition_penalty"] = user_settings.repeat_penalty
    else:
        payload["repeat_penalty"] = user_settings.repeat_penalty
        payload["reasoning_budget"] = 0  # Disable thinking/reasoning tokens

    assistant_content = ""

    # Tell the frontend which server is handling this request
    yield f"data: {json.dumps({'type': 'server_info', 'server_name': server_name})}\n\n"

    if context_overflow:
        yield f"data: {json.dumps({'type': 'context_warning', 'used': used_tokens, 'budget': ctx_budget})}\n\n"

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
                    yield f"data: {json.dumps({'type': 'error', 'content': f'LLM server error: {error_text.decode()}'})}\n\n"
                    return

                # Buffer to strip <think>...</think> and <thinking>...</thinking>
                # blocks from reasoning models.
                # Longest tag is </thinking> (11 chars); keep 12 in the tail
                # buffer so partial tags are never flushed prematurely.
                TAIL_SIZE = 12
                token_buffer = ""
                in_think = False

                def _find_open(text):
                    """Return (pos, tag_len) of first think-open tag, or None."""
                    best = None
                    for tag in ("<thinking>", "<think>"):
                        p = text.find(tag)
                        if p != -1 and (best is None or p < best[0]):
                            best = (p, len(tag))
                    return best

                def _find_close(text):
                    """Return (pos, tag_len) of first think-close tag, or None."""
                    best = None
                    for tag in ("</thinking>", "</think>"):
                        p = text.find(tag)
                        if p != -1 and (best is None or p < best[0]):
                            best = (p, len(tag))
                    return best

                def _strip_close_tags(text):
                    return text.replace("</thinking>", "").replace("</think>", "")

                async for line in response.aiter_lines():
                    if not line:
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
                                    token_buffer += content

                                    # Strip think blocks
                                    if not in_think:
                                        match = _find_open(token_buffer)
                                        while match:
                                            pos, tag_len = match
                                            before = token_buffer[:pos]
                                            after = token_buffer[pos + tag_len:]
                                            close = _find_close(after)
                                            if close:
                                                # Full think block in buffer — remove it
                                                c_pos, c_len = close
                                                token_buffer = before + after[c_pos + c_len:]
                                                match = _find_open(token_buffer)
                                            else:
                                                # Open tag without close — enter think mode
                                                if before:
                                                    assistant_content += before
                                                    yield f"data: {json.dumps({'type': 'content', 'content': before})}\n\n"
                                                token_buffer = after
                                                in_think = True
                                                break

                                    if in_think:
                                        close = _find_close(token_buffer)
                                        if close:
                                            c_pos, c_len = close
                                            token_buffer = token_buffer[c_pos + c_len:]
                                            in_think = False
                                        else:
                                            # Keep tail for split close-tag detection
                                            if len(token_buffer) > TAIL_SIZE:
                                                token_buffer = token_buffer[-TAIL_SIZE:]
                                            continue

                                    token_buffer = _strip_close_tags(token_buffer)

                                    if in_think:
                                        continue

                                    # Flush buffer, keeping tail for partial open-tag detection
                                    if len(token_buffer) > TAIL_SIZE * 2:
                                        to_send = token_buffer[:-TAIL_SIZE]
                                        token_buffer = token_buffer[-TAIL_SIZE:]
                                        if to_send:
                                            assistant_content += to_send
                                            yield f"data: {json.dumps({'type': 'content', 'content': to_send})}\n\n"
                        except json.JSONDecodeError:
                            continue

                # Flush remaining buffer
                if token_buffer and not in_think:
                    token_buffer = _strip_close_tags(token_buffer)
                    if token_buffer:
                        assistant_content += token_buffer
                        yield f"data: {json.dumps({'type': 'content', 'content': token_buffer})}\n\n"

        # Save assistant message
        if assistant_content:
            message = await add_message(conversation_id, "assistant", assistant_content)

            # Auto-title conversation if it's the first exchange
            conversation = await get_conversation(conversation_id, user_id)
            if conversation and conversation.title == "New Conversation":
                # Use first ~50 chars of user message as title
                title = user_message[:50].strip()
                if len(user_message) > 50:
                    title += "..."
                await update_conversation(conversation_id, user_id, title)

            yield f"data: {json.dumps({'type': 'done', 'message_id': message.id})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'done', 'message_id': None})}\n\n"

    except httpx.ConnectError:
        yield f"data: {json.dumps({'type': 'error', 'content': 'Cannot connect to LLM server. Is llama.cpp running?'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"


@router.post("/{conversation_id}")
async def chat(conversation_id: int, data: ChatRequest, request: Request):
    """Send a message and stream the response."""
    user = await require_user(request)
    user_id = user["id"]
    ip = get_client_ip(request)

    # Verify conversation exists and belongs to user
    conversation = await get_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await log_activity(ip, "chat.message", f"Sent message in conversation {conversation_id}", user_id)
    return StreamingResponse(
        stream_chat_response(conversation_id, user_id, data.content, data.image, data.case_refs),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
