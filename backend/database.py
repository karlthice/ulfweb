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
    model_path TEXT,
    parallel INTEGER DEFAULT 1,
    ctx_size INTEGER DEFAULT 32768,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Collections (site-wide, admin-managed)
CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    embedding_model TEXT DEFAULT 'paraphrase-multilingual-mpnet-base-v2',
    is_default INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Documents in collections
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    collection_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    content_hash TEXT,
    file_size INTEGER,
    page_count INTEGER,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'ready', 'error')),
    error_message TEXT,
    uploaded_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
);

-- Text chunks from documents
CREATE TABLE IF NOT EXISTS document_chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,
    page_number INTEGER,
    context_prefix TEXT,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- GraphRAG entities
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY,
    collection_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    entity_type TEXT,
    attributes TEXT,
    embedding BLOB,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- GraphRAG relations
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY,
    collection_id INTEGER NOT NULL,
    source_entity_id INTEGER NOT NULL,
    target_entity_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    evidence TEXT,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (source_entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (target_entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

-- Entity-to-chunk linkage
CREATE TABLE IF NOT EXISTS entity_chunks (
    entity_id INTEGER NOT NULL,
    chunk_id INTEGER NOT NULL,
    PRIMARY KEY (entity_id, chunk_id),
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
);

-- Full-text search index for chunks (BM25 hybrid search)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content);

-- Auto-sync FTS index with document_chunks
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON document_chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON document_chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

-- Admin settings (singleton table for site-wide settings)
CREATE TABLE IF NOT EXISTS admin_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    document_ai_query_server_id INTEGER,
    document_ai_extraction_server_id INTEGER,
    document_ai_understanding_server_id INTEGER,
    FOREIGN KEY (document_ai_query_server_id) REFERENCES servers(id) ON DELETE SET NULL,
    FOREIGN KEY (document_ai_extraction_server_id) REFERENCES servers(id) ON DELETE SET NULL,
    FOREIGN KEY (document_ai_understanding_server_id) REFERENCES servers(id) ON DELETE SET NULL
);

-- Ensure admin_settings row exists
INSERT OR IGNORE INTO admin_settings (id) VALUES (1);

-- Indexes for document-related queries
CREATE INDEX IF NOT EXISTS idx_documents_collection_id ON documents(collection_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_entities_collection_id ON entities(collection_id);
CREATE INDEX IF NOT EXISTS idx_entities_document_id ON entities(document_id);
CREATE INDEX IF NOT EXISTS idx_relations_collection_id ON relations(collection_id);
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

        # Migration: Split document_ai_server_id into three separate fields
        cursor = await db.execute("PRAGMA table_info(admin_settings)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "document_ai_server_id" in columns:
            # Get the old value to migrate
            cursor = await db.execute(
                "SELECT document_ai_server_id FROM admin_settings WHERE id = 1"
            )
            row = await cursor.fetchone()
            old_server_id = row[0] if row else None

            # Add new columns if they don't exist
            if "document_ai_query_server_id" not in columns:
                await db.execute(
                    "ALTER TABLE admin_settings ADD COLUMN document_ai_query_server_id INTEGER"
                )
            if "document_ai_extraction_server_id" not in columns:
                await db.execute(
                    "ALTER TABLE admin_settings ADD COLUMN document_ai_extraction_server_id INTEGER"
                )
            if "document_ai_understanding_server_id" not in columns:
                await db.execute(
                    "ALTER TABLE admin_settings ADD COLUMN document_ai_understanding_server_id INTEGER"
                )

            # Migrate old value to all three new fields
            if old_server_id:
                await db.execute(
                    """UPDATE admin_settings SET
                       document_ai_query_server_id = ?,
                       document_ai_extraction_server_id = ?,
                       document_ai_understanding_server_id = ?
                       WHERE id = 1""",
                    (old_server_id, old_server_id, old_server_id)
                )
            await db.commit()

        # Migration: Add model_path and parallel columns to servers if not exists
        cursor = await db.execute("PRAGMA table_info(servers)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "model_path" not in columns:
            await db.execute(
                "ALTER TABLE servers ADD COLUMN model_path TEXT"
            )
            await db.commit()
        if "parallel" not in columns:
            await db.execute(
                "ALTER TABLE servers ADD COLUMN parallel INTEGER DEFAULT 1"
            )
            await db.commit()
        if "ctx_size" not in columns:
            await db.execute(
                "ALTER TABLE servers ADD COLUMN ctx_size INTEGER DEFAULT 32768"
            )
            await db.commit()

        # Migration: Add page_number and context_prefix to document_chunks
        cursor = await db.execute("PRAGMA table_info(document_chunks)")
        dc_columns = [row[1] for row in await cursor.fetchall()]
        if "page_number" not in dc_columns:
            await db.execute(
                "ALTER TABLE document_chunks ADD COLUMN page_number INTEGER"
            )
            await db.commit()
        if "context_prefix" not in dc_columns:
            await db.execute(
                "ALTER TABLE document_chunks ADD COLUMN context_prefix TEXT"
            )
            await db.commit()

        # Migration: Add skip_contextual_retrieval to admin_settings
        cursor = await db.execute("PRAGMA table_info(admin_settings)")
        admin_columns = [row[1] for row in await cursor.fetchall()]
        if "skip_contextual_retrieval" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN skip_contextual_retrieval INTEGER DEFAULT 0"
            )
            await db.commit()

        # Migration: Populate FTS index for existing chunks
        cursor = await db.execute("SELECT COUNT(*) FROM document_chunks")
        chunk_count = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM chunks_fts")
        fts_count = (await cursor.fetchone())[0]
        if chunk_count > 0 and fts_count == 0:
            await db.execute(
                "INSERT INTO chunks_fts(rowid, content) "
                "SELECT id, content FROM document_chunks"
            )
            await db.commit()

        # Create Default collection if not exists
        cursor = await db.execute(
            "SELECT id FROM collections WHERE is_default = 1"
        )
        if not await cursor.fetchone():
            await db.execute(
                """INSERT INTO collections (name, description, is_default)
                   VALUES (?, ?, 1)""",
                ("Default", "Default document collection")
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
