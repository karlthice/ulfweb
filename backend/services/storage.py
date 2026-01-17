"""Database operations for ulfweb."""

from datetime import datetime
from typing import Any

import aiosqlite

from backend.config import settings
from backend.database import get_db
from backend.models import (
    Conversation,
    ConversationWithMessages,
    Message,
    UserSettings,
)


async def get_or_create_user(ip_address: str) -> int:
    """Get or create a user by IP address, returns user ID."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM users WHERE ip_address = ?",
            (ip_address,)
        )
        row = await cursor.fetchone()

        if row:
            return row["id"]

        cursor = await db.execute(
            "INSERT INTO users (ip_address) VALUES (?)",
            (ip_address,)
        )
        await db.commit()
        return cursor.lastrowid


# Conversation operations
async def list_conversations(user_id: int) -> list[Conversation]:
    """List all conversations for a user, ordered by most recent."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, user_id, title, created_at, updated_at
               FROM conversations
               WHERE user_id = ?
               ORDER BY updated_at DESC""",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [Conversation(**dict(row)) for row in rows]


async def create_conversation(user_id: int, title: str = "New Conversation") -> Conversation:
    """Create a new conversation."""
    async with get_db() as db:
        now = datetime.utcnow()
        cursor = await db.execute(
            """INSERT INTO conversations (user_id, title, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, title, now, now)
        )
        await db.commit()

        return Conversation(
            id=cursor.lastrowid,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now
        )


async def get_conversation(conversation_id: int, user_id: int) -> ConversationWithMessages | None:
    """Get a conversation with all its messages."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, user_id, title, created_at, updated_at
               FROM conversations
               WHERE id = ? AND user_id = ?""",
            (conversation_id, user_id)
        )
        row = await cursor.fetchone()

        if not row:
            return None

        conversation = ConversationWithMessages(**dict(row))

        cursor = await db.execute(
            """SELECT id, conversation_id, role, content, created_at
               FROM messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC""",
            (conversation_id,)
        )
        messages = await cursor.fetchall()
        conversation.messages = [Message(**dict(msg)) for msg in messages]

        return conversation


async def update_conversation(conversation_id: int, user_id: int, title: str) -> Conversation | None:
    """Update a conversation's title."""
    async with get_db() as db:
        now = datetime.utcnow()
        cursor = await db.execute(
            """UPDATE conversations
               SET title = ?, updated_at = ?
               WHERE id = ? AND user_id = ?""",
            (title, now, conversation_id, user_id)
        )
        await db.commit()

        if cursor.rowcount == 0:
            return None

        cursor = await db.execute(
            """SELECT id, user_id, title, created_at, updated_at
               FROM conversations
               WHERE id = ?""",
            (conversation_id,)
        )
        row = await cursor.fetchone()
        return Conversation(**dict(row)) if row else None


async def delete_conversation(conversation_id: int, user_id: int) -> bool:
    """Delete a conversation and all its messages."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def touch_conversation(conversation_id: int) -> None:
    """Update the conversation's updated_at timestamp."""
    async with get_db() as db:
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (datetime.utcnow(), conversation_id)
        )
        await db.commit()


# Message operations
async def add_message(conversation_id: int, role: str, content: str) -> Message:
    """Add a message to a conversation."""
    async with get_db() as db:
        now = datetime.utcnow()
        cursor = await db.execute(
            """INSERT INTO messages (conversation_id, role, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (conversation_id, role, content, now)
        )
        await db.commit()

        # Update conversation timestamp
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id)
        )
        await db.commit()

        return Message(
            id=cursor.lastrowid,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now
        )


async def get_conversation_messages(conversation_id: int) -> list[Message]:
    """Get all messages for a conversation."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, conversation_id, role, content, created_at
               FROM messages
               WHERE conversation_id = ?
               ORDER BY created_at ASC""",
            (conversation_id,)
        )
        rows = await cursor.fetchall()
        return [Message(**dict(row)) for row in rows]


# Settings operations
async def get_user_settings(user_id: int) -> UserSettings:
    """Get user settings, creating defaults if not exists."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT temperature, top_k, top_p, repeat_penalty, max_tokens, system_prompt
               FROM user_settings
               WHERE user_id = ?""",
            (user_id,)
        )
        row = await cursor.fetchone()

        if row:
            return UserSettings(**dict(row))

        # Create default settings
        defaults = settings.defaults
        await db.execute(
            """INSERT INTO user_settings
               (user_id, temperature, top_k, top_p, repeat_penalty, max_tokens, system_prompt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, defaults.temperature, defaults.top_k, defaults.top_p,
             defaults.repeat_penalty, defaults.max_tokens, defaults.system_prompt)
        )
        await db.commit()

        return UserSettings(
            temperature=defaults.temperature,
            top_k=defaults.top_k,
            top_p=defaults.top_p,
            repeat_penalty=defaults.repeat_penalty,
            max_tokens=defaults.max_tokens,
            system_prompt=defaults.system_prompt
        )


async def update_user_settings(user_id: int, updates: dict[str, Any]) -> UserSettings:
    """Update user settings."""
    # Ensure settings exist
    await get_user_settings(user_id)

    async with get_db() as db:
        # Build update query dynamically
        set_clauses = []
        values = []
        for key, value in updates.items():
            if value is not None:
                set_clauses.append(f"{key} = ?")
                values.append(value)

        if set_clauses:
            values.append(user_id)
            await db.execute(
                f"UPDATE user_settings SET {', '.join(set_clauses)} WHERE user_id = ?",
                values
            )
            await db.commit()

        return await get_user_settings(user_id)
