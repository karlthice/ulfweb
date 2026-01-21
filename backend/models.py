"""Pydantic models for request/response validation."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# Message models
class MessageBase(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class Message(MessageBase):
    id: int
    conversation_id: int
    created_at: datetime


class MessageCreate(BaseModel):
    content: str


# Conversation models
class ConversationBase(BaseModel):
    title: str = "New Conversation"


class Conversation(ConversationBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class ConversationWithMessages(Conversation):
    messages: list[Message] = []


class ConversationCreate(BaseModel):
    title: str = "New Conversation"


class ConversationUpdate(BaseModel):
    title: str


# Settings models
class UserSettings(BaseModel):
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_k: int = Field(default=40, ge=1, le=100)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=1.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1, le=8192)
    system_prompt: str = ""
    model: str = ""


class UserSettingsUpdate(BaseModel):
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_k: int | None = Field(default=None, ge=1, le=100)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    repeat_penalty: float | None = Field(default=None, ge=1.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    system_prompt: str | None = None
    model: str | None = None


# Model listing models (for llama.cpp /v1/models endpoint)
class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "llama.cpp"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo] = []


# Chat models
class ChatRequest(BaseModel):
    content: str
    image: str | None = None  # Optional base64-encoded image for vision models


class ChatChunk(BaseModel):
    """SSE chunk format for streaming responses."""
    type: Literal["content", "done", "error"]
    content: str = ""
    message_id: int | None = None


# Translation models
class TranslateRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str


# Server models (site-wide LLM backends)
class ServerBase(BaseModel):
    friendly_name: str
    url: str
    active: bool = True


class Server(ServerBase):
    id: int
    created_at: datetime


class ServerCreate(ServerBase):
    pass


class ServerUpdate(BaseModel):
    friendly_name: str | None = None
    url: str | None = None
    active: bool | None = None


# Document status enum
class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


# Collection models
class CollectionBase(BaseModel):
    name: str
    description: str = ""


class Collection(CollectionBase):
    id: int
    embedding_model: str = "paraphrase-multilingual-mpnet-base-v2"
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class CollectionWithStats(Collection):
    document_count: int = 0


class CollectionCreate(CollectionBase):
    pass


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


# Document models
class DocumentBase(BaseModel):
    original_filename: str


class Document(DocumentBase):
    id: int
    collection_id: int
    filename: str
    content_hash: str | None = None
    file_size: int | None = None
    page_count: int | None = None
    status: DocumentStatus = DocumentStatus.PENDING
    error_message: str | None = None
    uploaded_by: str | None = None
    created_at: datetime


class DocumentStatusResponse(BaseModel):
    id: int
    status: DocumentStatus
    error_message: str | None = None
    page_count: int | None = None


# Document query models
class DocumentQuery(BaseModel):
    question: str
    top_k: int = Field(default=5, ge=1, le=20)


class QueryChunk(BaseModel):
    type: Literal["content", "sources", "done", "error"]
    content: str = ""
    sources: list[str] = []


# Admin settings models
class AdminSettings(BaseModel):
    document_ai_query_server_id: int | None = None
    document_ai_extraction_server_id: int | None = None
    document_ai_understanding_server_id: int | None = None


class AdminSettingsUpdate(BaseModel):
    document_ai_query_server_id: int | None = None
    document_ai_extraction_server_id: int | None = None
    document_ai_understanding_server_id: int | None = None
