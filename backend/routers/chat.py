"""Chat endpoint with SSE streaming."""

import json
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.config import settings
from backend.models import ChatRequest
from backend.services.storage import (
    add_message,
    get_conversation,
    get_conversation_messages,
    get_or_create_user,
    get_user_settings,
    touch_conversation,
    update_conversation,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


async def stream_chat_response(
    conversation_id: int,
    user_id: int,
    user_message: str
) -> AsyncGenerator[str, None]:
    """Stream chat response from llama.cpp server."""
    # Save user message
    await add_message(conversation_id, "user", user_message)

    # Get conversation messages and user settings
    messages = await get_conversation_messages(conversation_id)
    user_settings = await get_user_settings(user_id)

    # Build messages for llama.cpp API
    llama_messages = []

    # Add system prompt if set
    if user_settings.system_prompt:
        llama_messages.append({
            "role": "system",
            "content": user_settings.system_prompt
        })

    # Add conversation history
    for msg in messages:
        llama_messages.append({
            "role": msg.role,
            "content": msg.content
        })

    # Build request payload
    payload = {
        "messages": llama_messages,
        "stream": True,
        "temperature": user_settings.temperature,
        "top_k": user_settings.top_k,
        "top_p": user_settings.top_p,
        "repeat_penalty": user_settings.repeat_penalty,
        "max_tokens": user_settings.max_tokens,
    }

    assistant_content = ""

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{settings.llama.url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    yield f"data: {json.dumps({'type': 'error', 'content': f'LLM server error: {error_text.decode()}'})}\n\n"
                    return

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
                                    assistant_content += content
                                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                        except json.JSONDecodeError:
                            continue

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
    ip = get_client_ip(request)
    user_id = await get_or_create_user(ip)

    # Verify conversation exists and belongs to user
    conversation = await get_conversation(conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return StreamingResponse(
        stream_chat_response(conversation_id, user_id, data.content),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
