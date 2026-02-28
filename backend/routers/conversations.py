"""Conversation CRUD endpoints."""

from fastapi import APIRouter, HTTPException, Request

from backend.auth import get_client_ip, require_user
from backend.models import (
    Conversation,
    ConversationCreate,
    ConversationUpdate,
    ConversationWithMessages,
)
from backend.services.storage import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    log_activity,
    update_conversation,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[Conversation])
async def list_user_conversations(request: Request):
    """List all conversations for the current user."""
    user = await require_user(request)
    return await list_conversations(user["id"])


@router.post("", response_model=Conversation, status_code=201)
async def create_new_conversation(request: Request, data: ConversationCreate = None):
    """Create a new conversation."""
    user = await require_user(request)
    ip = get_client_ip(request)
    title = data.title if data else "New Conversation"
    conv = await create_conversation(user["id"], title)
    await log_activity(ip, "conversation.create", f"Created conversation '{title}'", user["id"])
    return conv


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation_detail(conversation_id: int, request: Request):
    """Get a conversation with all its messages."""
    user = await require_user(request)
    conversation = await get_conversation(conversation_id, user["id"])
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.put("/{conversation_id}", response_model=Conversation)
async def update_conversation_title(
    conversation_id: int,
    data: ConversationUpdate,
    request: Request
):
    """Update a conversation's title."""
    user = await require_user(request)
    ip = get_client_ip(request)
    conversation = await update_conversation(conversation_id, user["id"], data.title)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await log_activity(ip, "conversation.rename", f"Renamed conversation to '{data.title}'", user["id"])
    return conversation


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation_endpoint(conversation_id: int, request: Request):
    """Delete a conversation and all its messages."""
    user = await require_user(request)
    ip = get_client_ip(request)
    deleted = await delete_conversation(conversation_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await log_activity(ip, "conversation.delete", f"Deleted conversation {conversation_id}", user["id"])
