"""SQLite database initialization and connection management."""

import logging
import shutil

import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from backend.config import settings
from backend.auth import hash_password
from backend.encryption import get_db_key, init_encryption_key, is_encrypted

logger = logging.getLogger("ulfweb")


def _make_encrypted_connector(db_path: str | Path, hex_key: str):
    """Return a callable that creates an encrypted SQLCipher connection."""
    from sqlcipher3 import dbapi2 as sqlcipher

    def connector():
        conn = sqlcipher.connect(str(db_path))
        conn.execute(f"PRAGMA key=\"x'{hex_key}'\"")
        return conn
    return connector


def _migrate_to_encrypted(db_path: Path, hex_key: str) -> None:
    """Migrate an unencrypted SQLite database to SQLCipher in-place."""
    from sqlcipher3 import dbapi2 as sqlcipher

    # Test if the DB is unencrypted by trying to read it without a key
    try:
        conn = sqlcipher.connect(str(db_path))
        conn.execute("SELECT count(*) FROM sqlite_master")
        # If we get here, the DB is unencrypted (readable without key)
        conn.close()
    except Exception:
        # DB is either encrypted already or doesn't exist — nothing to migrate
        return

    logger.info("Migrating unencrypted database to SQLCipher...")
    encrypted_path = db_path.with_suffix(".db.encrypted")

    conn = sqlcipher.connect(str(db_path))
    try:
        conn.execute(f"ATTACH DATABASE '{encrypted_path}' AS encrypted KEY \"x'{hex_key}'\"")
        conn.execute("SELECT sqlcipher_export('encrypted')")
        conn.execute("DETACH DATABASE encrypted")
    finally:
        conn.close()

    # Replace original with encrypted copy
    backup_path = db_path.with_suffix(".db.unencrypted_backup")
    shutil.move(str(db_path), str(backup_path))
    shutil.move(str(encrypted_path), str(db_path))
    logger.info(
        "Database migration complete. Unencrypted backup saved as %s — "
        "delete it once you've verified encryption works.",
        backup_path,
    )


SCHEMA = """
-- Users with username/password authentication
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    usertype TEXT NOT NULL DEFAULT 'normal',
    full_name TEXT DEFAULT '',
    description TEXT DEFAULT '',
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sessions for cookie-based auth
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
    date_format TEXT DEFAULT 'YYYY-MM-DD',
    single_user TEXT DEFAULT '',
    FOREIGN KEY (document_ai_query_server_id) REFERENCES servers(id) ON DELETE SET NULL,
    FOREIGN KEY (document_ai_extraction_server_id) REFERENCES servers(id) ON DELETE SET NULL,
    FOREIGN KEY (document_ai_understanding_server_id) REFERENCES servers(id) ON DELETE SET NULL
);

-- Ensure admin_settings row exists
INSERT OR IGNORE INTO admin_settings (id) VALUES (1);

-- Vault cases
CREATE TABLE IF NOT EXISTS vault_cases (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    identifier TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_public INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'closed', 'archived')),
    ai_summary TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Vault records
CREATE TABLE IF NOT EXISTS vault_records (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL,
    created_by_user_id INTEGER,
    record_type TEXT NOT NULL CHECK(record_type IN ('text', 'document', 'image')),
    title TEXT DEFAULT '',
    content TEXT,
    filename TEXT,
    original_filename TEXT,
    file_size INTEGER,
    ai_description TEXT,
    starred INTEGER DEFAULT 0,
    record_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES vault_cases(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

-- Indexes for document-related queries
CREATE INDEX IF NOT EXISTS idx_documents_collection_id ON documents(collection_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_entities_collection_id ON entities(collection_id);
CREATE INDEX IF NOT EXISTS idx_entities_document_id ON entities(document_id);
CREATE INDEX IF NOT EXISTS idx_relations_collection_id ON relations(collection_id);

-- Vault indexes
CREATE INDEX IF NOT EXISTS idx_vault_cases_user_id ON vault_cases(user_id);
CREATE INDEX IF NOT EXISTS idx_vault_cases_public ON vault_cases(is_public);
CREATE INDEX IF NOT EXISTS idx_vault_records_case_id ON vault_records(case_id);
CREATE INDEX IF NOT EXISTS idx_vault_records_starred ON vault_records(starred);

-- Activity log
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    user_ip TEXT NOT NULL,
    action_type TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_activity_log_created_at ON activity_log(created_at);
CREATE INDEX IF NOT EXISTS idx_activity_log_action_type ON activity_log(action_type);
CREATE INDEX IF NOT EXISTS idx_activity_log_user_ip ON activity_log(user_ip);
"""


async def init_database() -> None:
    """Initialize the database with schema."""
    db_path = Path(settings.database.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize encryption key (generates on first run)
    init_encryption_key()

    # Migrate existing unencrypted DB if needed
    if is_encrypted() and db_path.exists():
        _migrate_to_encrypted(db_path, get_db_key())

    if is_encrypted():
        connector = _make_encrypted_connector(db_path, get_db_key())
        db_ctx = aiosqlite.Connection(connector, iter_chunk_size=64)
    else:
        db_ctx = aiosqlite.connect(db_path)

    async with db_ctx as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
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
        if "autoload" not in columns:
            await db.execute(
                "ALTER TABLE servers ADD COLUMN autoload INTEGER DEFAULT 0"
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

        # Migration: Add translation_server_id to admin_settings
        cursor = await db.execute("PRAGMA table_info(admin_settings)")
        admin_columns = [row[1] for row in await cursor.fetchall()]
        if "translation_server_id" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN translation_server_id INTEGER"
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

        # Migration: Add whisper_model to admin_settings
        cursor = await db.execute("PRAGMA table_info(admin_settings)")
        admin_columns = [row[1] for row in await cursor.fetchall()]
        if "whisper_model" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN whisper_model TEXT DEFAULT 'large-v3-turbo'"
            )
            await db.commit()

        # Migration: Add vault server settings to admin_settings
        cursor = await db.execute("PRAGMA table_info(admin_settings)")
        admin_columns = [row[1] for row in await cursor.fetchall()]
        if "vault_image_server_id" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN vault_image_server_id INTEGER"
            )
            await db.commit()
        if "vault_text_server_id" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN vault_text_server_id INTEGER"
            )
            await db.commit()

        # Migration: Add vault_chat_records to admin_settings
        if "vault_chat_records" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN vault_chat_records INTEGER DEFAULT 10"
            )
            await db.commit()

        # Migration: Add date_format to admin_settings
        cursor = await db.execute("PRAGMA table_info(admin_settings)")
        admin_columns = [row[1] for row in await cursor.fetchall()]
        if "date_format" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN date_format TEXT DEFAULT 'YYYY-MM-DD'"
            )
            await db.commit()

        # Migration: Add ai_summary to vault_cases
        cursor = await db.execute("PRAGMA table_info(vault_cases)")
        vault_columns = [row[1] for row in await cursor.fetchall()]
        if "ai_summary" not in vault_columns:
            await db.execute(
                "ALTER TABLE vault_cases ADD COLUMN ai_summary TEXT DEFAULT ''"
            )
            await db.commit()

        # Migration: Add created_by_user_id to vault_records
        cursor = await db.execute("PRAGMA table_info(vault_records)")
        vr_columns = [row[1] for row in await cursor.fetchall()]
        if "created_by_user_id" not in vr_columns:
            await db.execute(
                "ALTER TABLE vault_records ADD COLUMN created_by_user_id INTEGER"
            )
            # Backfill: set created_by_user_id to the case owner for existing records
            await db.execute(
                """UPDATE vault_records SET created_by_user_id = (
                       SELECT user_id FROM vault_cases WHERE vault_cases.id = vault_records.case_id
                   )"""
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

        # Migration: users table - migrate from IP-based to username/password
        cursor = await db.execute("PRAGMA table_info(users)")
        user_columns = [row[1] for row in await cursor.fetchall()]
        if "ip_address" in user_columns:
            # Old schema - drop all IP-based data and recreate
            await db.execute("DELETE FROM activity_log")
            await db.execute("DELETE FROM vault_records")
            await db.execute("DELETE FROM vault_cases")
            await db.execute("DELETE FROM messages")
            await db.execute("DELETE FROM conversations")
            await db.execute("DELETE FROM user_settings")
            await db.execute("DELETE FROM users")
            await db.execute("DROP TABLE IF EXISTS users")
            await db.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    usertype TEXT NOT NULL DEFAULT 'normal',
                    full_name TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create sessions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            await db.commit()

        # Migration: Add single_user to admin_settings
        cursor = await db.execute("PRAGMA table_info(admin_settings)")
        admin_columns = [row[1] for row in await cursor.fetchall()]
        if "single_user" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN single_user TEXT DEFAULT ''"
            )
            await db.commit()

        # Migration: Add chat_server_id to admin_settings
        cursor = await db.execute("PRAGMA table_info(admin_settings)")
        admin_columns = [row[1] for row in await cursor.fetchall()]
        if "chat_server_id" not in admin_columns:
            await db.execute(
                "ALTER TABLE admin_settings ADD COLUMN chat_server_id INTEGER"
            )
            await db.commit()

        # Migration: Append mermaid instruction to existing system prompts
        mermaid_hint = "When asked to create diagrams, charts, or flowcharts, use mermaid syntax in a ```mermaid code block."
        await db.execute(
            """UPDATE user_settings
               SET system_prompt = CASE
                   WHEN system_prompt IS NULL OR system_prompt = '' THEN ?
                   ELSE system_prompt || ' ' || ?
               END
               WHERE system_prompt NOT LIKE '%mermaid%'""",
            (mermaid_hint, mermaid_hint)
        )
        await db.commit()

        # Create default admin user if no users exist
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        user_count = (await cursor.fetchone())[0]
        if user_count == 0:
            admin_hash = hash_password("admin")
            await db.execute(
                """INSERT INTO users (username, usertype, full_name, password_hash)
                   VALUES (?, ?, ?, ?)""",
                ("admin", "admin", "Administrator", admin_hash)
            )
            # Set single_user to 'admin' so app works immediately without login
            await db.execute(
                "UPDATE admin_settings SET single_user = 'admin' WHERE id = 1"
            )
            await db.commit()

        # Clean up expired sessions
        await db.execute(
            "DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP"
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
    if is_encrypted():
        from sqlcipher3 import dbapi2 as sqlcipher
        connector = _make_encrypted_connector(settings.database.path, get_db_key())
        db = aiosqlite.Connection(connector, iter_chunk_size=64)
        await db.__aenter__()
        db.row_factory = sqlcipher.Row
    else:
        db = aiosqlite.connect(settings.database.path)
        await db.__aenter__()
        db.row_factory = aiosqlite.Row
    # Override LOWER() to handle Unicode (SQLite built-in only handles ASCII)
    await db.create_function("LOWER", 1, lambda s: s.lower() if s else s)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    try:
        yield db
    finally:
        await db.close()
