"""SQLite database initialization and connection management."""

import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from backend.config import settings


SCHEMA = """
-- Users identified by IP
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    ip_address TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User settings
CREATE TABLE IF NOT EXISTS user_settings (
    id INTEGER PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL,
    temperature REAL DEFAULT 0.7,
    top_k INTEGER DEFAULT 40,
    top_p REAL DEFAULT 0.9,
    repeat_penalty REAL DEFAULT 1.1,
    max_tokens INTEGER DEFAULT 2048,
    system_prompt TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    title TEXT DEFAULT 'New Conversation',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

-- Servers (site-wide LLM backends)
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY,
    friendly_name TEXT NOT NULL,
    url TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_database() -> None:
    """Initialize the database with schema."""
    db_path = Path(settings.database.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()

        # Migration: Add model column to user_settings if not exists
        cursor = await db.execute("PRAGMA table_info(user_settings)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "model" not in columns:
            await db.execute(
                "ALTER TABLE user_settings ADD COLUMN model TEXT DEFAULT ''"
            )
            await db.commit()


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Get a database connection."""
    db = await aiosqlite.connect(settings.database.path)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
