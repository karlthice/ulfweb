"""Conversation CRUD endpoints."""

from fastapi import APIRouter, HTTPException, Request

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
    get_or_create_user,
    list_conversations,
    update_conversation,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@router.get("", response_model=list[Conversation])
async def list_user_conversations(request: Request):
    """List all conversations for the current user."""
    ip = get_client_ip(request)
    user_id = await get_or_create_user(ip)
    return await list_conversations(user_id)


@router.post("", response_model=Conversation, status_code=201)
async def create_new_conversation(request: Request, data: ConversationCreate = None):
    """Create a new conversation."""
    ip = get_client_ip(request)
    user_id = await get_or_create_user(ip)
    title = data.title if data else "New Conversation"
    return await create_conversation(user_id, title)


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation_detail(conversation_id: int, request: Request):
    """Get a conversation with all its messages."""
    ip = get_client_ip(request)
    user_id = await get_or_create_user(ip)
    conversation = await get_conversation(conversation_id, user_id)
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
    ip = get_client_ip(request)
    user_id = await get_or_create_user(ip)
    conversation = await update_conversation(conversation_id, user_id, data.title)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation_endpoint(conversation_id: int, request: Request):
    """Delete a conversation and all its messages."""
    ip = get_client_ip(request)
    user_id = await get_or_create_user(ip)
    deleted = await delete_conversation(conversation_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
