"""Database operations for ulfweb."""

from datetime import datetime
from typing import Any

import aiosqlite

from backend.config import settings
from backend.database import get_db
from backend.models import (
    AdminSettings,
    Collection,
    CollectionWithStats,
    Conversation,
    ConversationWithMessages,
    Document,
    DocumentStatus,
    DocumentStatusResponse,
    Message,
    Server,
    UserSettings,
    VaultCase,
    VaultCaseWithRecords,
    VaultRecord,
)


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
            """SELECT temperature, top_k, top_p, repeat_penalty, max_tokens, system_prompt, model
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
               (user_id, temperature, top_k, top_p, repeat_penalty, max_tokens, system_prompt, model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, defaults.temperature, defaults.top_k, defaults.top_p,
             defaults.repeat_penalty, defaults.max_tokens, defaults.system_prompt, defaults.model)
        )
        await db.commit()

        return UserSettings(
            temperature=defaults.temperature,
            top_k=defaults.top_k,
            top_p=defaults.top_p,
            repeat_penalty=defaults.repeat_penalty,
            max_tokens=defaults.max_tokens,
            system_prompt=defaults.system_prompt,
            model=defaults.model
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


# Server operations (site-wide)
async def list_servers(active_only: bool = False) -> list[Server]:
    """List all servers, optionally filtering by active status."""
    async with get_db() as db:
        if active_only:
            cursor = await db.execute(
                """SELECT id, friendly_name, url, active, model_path, parallel, ctx_size, created_at
                   FROM servers WHERE active = 1
                   ORDER BY friendly_name ASC"""
            )
        else:
            cursor = await db.execute(
                """SELECT id, friendly_name, url, active, model_path, parallel, ctx_size, created_at
                   FROM servers
                   ORDER BY friendly_name ASC"""
            )
        rows = await cursor.fetchall()
        return [Server(**dict(row)) for row in rows]


async def get_server(server_id: int) -> Server | None:
    """Get a server by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, friendly_name, url, active, model_path, parallel, ctx_size, created_at
               FROM servers WHERE id = ?""",
            (server_id,)
        )
        row = await cursor.fetchone()
        return Server(**dict(row)) if row else None


async def create_server(
    friendly_name: str,
    url: str,
    active: bool = True,
    model_path: str | None = None,
    parallel: int = 1,
    ctx_size: int = 32768
) -> Server:
    """Create a new server."""
    async with get_db() as db:
        from datetime import datetime
        now = datetime.utcnow()
        cursor = await db.execute(
            """INSERT INTO servers (friendly_name, url, active, model_path, parallel, ctx_size, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (friendly_name, url, 1 if active else 0, model_path, parallel, ctx_size, now)
        )
        await db.commit()
        return Server(
            id=cursor.lastrowid,
            friendly_name=friendly_name,
            url=url,
            active=active,
            model_path=model_path,
            parallel=parallel,
            ctx_size=ctx_size,
            created_at=now
        )


async def update_server(server_id: int, updates: dict[str, Any]) -> Server | None:
    """Update a server's properties."""
    async with get_db() as db:
        set_clauses = []
        values = []
        valid_keys = ("friendly_name", "url", "active", "model_path", "parallel", "ctx_size")
        for key, value in updates.items():
            if key not in valid_keys:
                continue
            if value is not None:
                if key == "active":
                    set_clauses.append(f"{key} = ?")
                    values.append(1 if value else 0)
                else:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
            elif key == "model_path":
                # Allow explicitly setting model_path to None
                set_clauses.append(f"{key} = ?")
                values.append(None)

        if not set_clauses:
            return await get_server(server_id)

        values.append(server_id)
        await db.execute(
            f"UPDATE servers SET {', '.join(set_clauses)} WHERE id = ?",
            values
        )
        await db.commit()
        return await get_server(server_id)


async def delete_server(server_id: int) -> bool:
    """Delete a server."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM servers WHERE id = ?",
            (server_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# Collection operations
async def list_collections() -> list[CollectionWithStats]:
    """List all collections with document counts."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT c.id, c.name, c.description, c.embedding_model, c.is_default,
                      c.created_at, c.updated_at,
                      COUNT(d.id) as document_count
               FROM collections c
               LEFT JOIN documents d ON d.collection_id = c.id
               GROUP BY c.id
               ORDER BY c.is_default DESC, c.name ASC"""
        )
        rows = await cursor.fetchall()
        return [CollectionWithStats(**dict(row)) for row in rows]


async def get_collection(collection_id: int) -> CollectionWithStats | None:
    """Get a collection by ID with document count."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT c.id, c.name, c.description, c.embedding_model, c.is_default,
                      c.created_at, c.updated_at,
                      COUNT(d.id) as document_count
               FROM collections c
               LEFT JOIN documents d ON d.collection_id = c.id
               WHERE c.id = ?
               GROUP BY c.id""",
            (collection_id,)
        )
        row = await cursor.fetchone()
        return CollectionWithStats(**dict(row)) if row else None


async def create_collection(name: str, description: str = "") -> Collection:
    """Create a new collection."""
    async with get_db() as db:
        now = datetime.utcnow()
        cursor = await db.execute(
            """INSERT INTO collections (name, description, created_at, updated_at)
               VALUES (?, ?, ?, ?)""",
            (name, description, now, now)
        )
        await db.commit()
        return Collection(
            id=cursor.lastrowid,
            name=name,
            description=description,
            embedding_model="paraphrase-multilingual-mpnet-base-v2",
            is_default=False,
            created_at=now,
            updated_at=now
        )


async def update_collection(collection_id: int, updates: dict[str, Any]) -> Collection | None:
    """Update a collection's properties."""
    async with get_db() as db:
        set_clauses = ["updated_at = ?"]
        values = [datetime.utcnow()]

        for key, value in updates.items():
            if value is not None and key in ("name", "description"):
                set_clauses.append(f"{key} = ?")
                values.append(value)

        values.append(collection_id)
        await db.execute(
            f"UPDATE collections SET {', '.join(set_clauses)} WHERE id = ?",
            values
        )
        await db.commit()

        cursor = await db.execute(
            """SELECT id, name, description, embedding_model, is_default, created_at, updated_at
               FROM collections WHERE id = ?""",
            (collection_id,)
        )
        row = await cursor.fetchone()
        return Collection(**dict(row)) if row else None


async def delete_collection(collection_id: int) -> bool:
    """Delete a collection (cannot delete default)."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM collections WHERE id = ? AND is_default = 0",
            (collection_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# Document operations
async def list_documents(collection_id: int) -> list[Document]:
    """List all documents in a collection."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, collection_id, filename, original_filename, content_hash,
                      file_size, page_count, status, error_message, uploaded_by, created_at
               FROM documents
               WHERE collection_id = ?
               ORDER BY created_at DESC""",
            (collection_id,)
        )
        rows = await cursor.fetchall()
        return [Document(**dict(row)) for row in rows]


async def get_document(document_id: int) -> Document | None:
    """Get a document by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, collection_id, filename, original_filename, content_hash,
                      file_size, page_count, status, error_message, uploaded_by, created_at
               FROM documents WHERE id = ?""",
            (document_id,)
        )
        row = await cursor.fetchone()
        return Document(**dict(row)) if row else None


async def create_document(
    collection_id: int,
    filename: str,
    original_filename: str,
    content_hash: str,
    file_size: int,
    uploaded_by: str | None = None
) -> Document:
    """Create a new document record."""
    async with get_db() as db:
        now = datetime.utcnow()
        cursor = await db.execute(
            """INSERT INTO documents (collection_id, filename, original_filename, content_hash,
                                     file_size, status, uploaded_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (collection_id, filename, original_filename, content_hash, file_size, "pending", uploaded_by, now)
        )
        await db.commit()
        return Document(
            id=cursor.lastrowid,
            collection_id=collection_id,
            filename=filename,
            original_filename=original_filename,
            content_hash=content_hash,
            file_size=file_size,
            page_count=None,
            status=DocumentStatus.PENDING,
            error_message=None,
            uploaded_by=uploaded_by,
            created_at=now
        )


async def update_document_status(
    document_id: int,
    status: str,
    error_message: str | None = None,
    page_count: int | None = None
) -> DocumentStatusResponse | None:
    """Update a document's processing status."""
    async with get_db() as db:
        set_clauses = ["status = ?"]
        values = [status]

        if error_message is not None:
            set_clauses.append("error_message = ?")
            values.append(error_message)

        if page_count is not None:
            set_clauses.append("page_count = ?")
            values.append(page_count)

        values.append(document_id)
        await db.execute(
            f"UPDATE documents SET {', '.join(set_clauses)} WHERE id = ?",
            values
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT id, status, error_message, page_count FROM documents WHERE id = ?",
            (document_id,)
        )
        row = await cursor.fetchone()
        return DocumentStatusResponse(**dict(row)) if row else None


async def delete_document(document_id: int) -> bool:
    """Delete a document and all related data."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM documents WHERE id = ?",
            (document_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


# Chunk operations
async def bulk_insert_chunks(document_id: int, chunks: list[dict]) -> None:
    """Insert multiple chunks for a document."""
    async with get_db() as db:
        for idx, chunk in enumerate(chunks):
            await db.execute(
                """INSERT INTO document_chunks
                   (document_id, chunk_index, content, embedding, page_number, context_prefix)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (document_id, idx, chunk["content"], chunk.get("embedding"),
                 chunk.get("page_number"), chunk.get("context_prefix"))
            )
        await db.commit()


async def get_chunks_by_document(document_id: int) -> list[dict]:
    """Get all chunks for a document."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, document_id, chunk_index, content, embedding, page_number
               FROM document_chunks
               WHERE document_id = ?
               ORDER BY chunk_index ASC""",
            (document_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_chunks_by_collection(collection_id: int) -> list[dict]:
    """Get all chunks for a collection."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT c.id, c.document_id, c.chunk_index, c.content, c.embedding,
                      c.page_number, d.original_filename
               FROM document_chunks c
               JOIN documents d ON d.id = c.document_id
               WHERE d.collection_id = ? AND d.status = 'ready'
               ORDER BY d.id, c.chunk_index""",
            (collection_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def search_chunks_fts(collection_id: int, query: str, limit: int = 50) -> list[tuple[int, float]]:
    """Search chunks using FTS5 BM25 ranking. Returns [(chunk_id, score), ...]."""
    import re as _re
    async with get_db() as db:
        clean_query = _re.sub(r'[^\w\s]', ' ', query).strip()
        words = clean_query.split()
        if not words:
            return []
        fts_query = " OR ".join(f'"{w}"' for w in words if w)
        try:
            cursor = await db.execute(
                """SELECT dc.id, bm25(chunks_fts) as score
                   FROM chunks_fts
                   JOIN document_chunks dc ON dc.id = chunks_fts.rowid
                   JOIN documents d ON d.id = dc.document_id
                   WHERE chunks_fts MATCH ? AND d.collection_id = ? AND d.status = 'ready'
                   ORDER BY score
                   LIMIT ?""",
                (fts_query, collection_id, limit)
            )
            rows = await cursor.fetchall()
            # bm25() returns negative scores (lower = better), negate for ranking
            return [(row["id"], -row["score"]) for row in rows]
        except Exception:
            return []


# Entity operations
async def bulk_insert_entities(collection_id: int, document_id: int, entities: list[dict]) -> list[int]:
    """Insert multiple entities, returns list of IDs."""
    entity_ids = []
    async with get_db() as db:
        for entity in entities:
            import json
            cursor = await db.execute(
                """INSERT INTO entities (collection_id, document_id, name, entity_type, attributes, embedding)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (collection_id, document_id, entity["name"], entity.get("entity_type"),
                 json.dumps(entity.get("attributes", {})), entity.get("embedding"))
            )
            entity_ids.append(cursor.lastrowid)
        await db.commit()
    return entity_ids


async def get_entities_by_collection(collection_id: int) -> list[dict]:
    """Get all entities for a collection with their embeddings."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT e.id, e.collection_id, e.document_id, e.name, e.entity_type, e.attributes, e.embedding,
                      d.original_filename
               FROM entities e
               JOIN documents d ON d.id = e.document_id
               WHERE e.collection_id = ? AND d.status = 'ready'""",
            (collection_id,)
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            import json
            r = dict(row)
            if r.get("attributes"):
                r["attributes"] = json.loads(r["attributes"])
            result.append(r)
        return result


# Relation operations
async def bulk_insert_relations(collection_id: int, relations: list[dict]) -> None:
    """Insert multiple relations."""
    async with get_db() as db:
        for rel in relations:
            await db.execute(
                """INSERT INTO relations (collection_id, source_entity_id, target_entity_id, relation_type, evidence)
                   VALUES (?, ?, ?, ?, ?)""",
                (collection_id, rel["source_entity_id"], rel["target_entity_id"],
                 rel["relation_type"], rel.get("evidence"))
            )
        await db.commit()


async def get_relations_by_collection(collection_id: int) -> list[dict]:
    """Get all relations for a collection."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT r.id, r.collection_id, r.source_entity_id, r.target_entity_id,
                      r.relation_type, r.evidence,
                      se.name as source_name, te.name as target_name
               FROM relations r
               JOIN entities se ON se.id = r.source_entity_id
               JOIN entities te ON te.id = r.target_entity_id
               WHERE r.collection_id = ?""",
            (collection_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# Entity-chunk linkage
async def link_entity_to_chunks(entity_id: int, chunk_ids: list[int]) -> None:
    """Link an entity to multiple chunks."""
    async with get_db() as db:
        for chunk_id in chunk_ids:
            await db.execute(
                "INSERT OR IGNORE INTO entity_chunks (entity_id, chunk_id) VALUES (?, ?)",
                (entity_id, chunk_id)
            )
        await db.commit()


async def get_chunks_for_entity(entity_id: int) -> list[int]:
    """Get chunk IDs linked to an entity."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT chunk_id FROM entity_chunks WHERE entity_id = ?",
            (entity_id,)
        )
        rows = await cursor.fetchall()
        return [row["chunk_id"] for row in rows]


# Admin settings operations
async def get_admin_settings() -> AdminSettings:
    """Get admin settings (singleton)."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT document_ai_query_server_id, document_ai_extraction_server_id,
                      document_ai_understanding_server_id, translation_server_id,
                      chat_server_id, skip_contextual_retrieval, whisper_model,
                      vault_image_server_id, vault_text_server_id,
                      date_format, single_user
               FROM admin_settings WHERE id = 1"""
        )
        row = await cursor.fetchone()
        if row:
            return AdminSettings(
                document_ai_query_server_id=row["document_ai_query_server_id"],
                document_ai_extraction_server_id=row["document_ai_extraction_server_id"],
                document_ai_understanding_server_id=row["document_ai_understanding_server_id"],
                translation_server_id=row["translation_server_id"],
                chat_server_id=row["chat_server_id"],
                skip_contextual_retrieval=bool(row["skip_contextual_retrieval"]),
                whisper_model=row["whisper_model"] or "large-v3-turbo",
                vault_image_server_id=row["vault_image_server_id"],
                vault_text_server_id=row["vault_text_server_id"],
                date_format=row["date_format"] or "YYYY-MM-DD",
                single_user=row["single_user"] or "",
            )
        return AdminSettings()


async def update_admin_settings(updates: dict[str, Any]) -> AdminSettings:
    """Update admin settings."""
    valid_keys = (
        "document_ai_query_server_id",
        "document_ai_extraction_server_id",
        "document_ai_understanding_server_id",
        "translation_server_id",
        "chat_server_id",
        "skip_contextual_retrieval",
        "whisper_model",
        "vault_image_server_id",
        "vault_text_server_id",
        "date_format",
        "single_user",
    )
    async with get_db() as db:
        # Ensure row exists
        await db.execute("INSERT OR IGNORE INTO admin_settings (id) VALUES (1)")

        set_clauses = []
        values = []
        for key, value in updates.items():
            if key in valid_keys:
                set_clauses.append(f"{key} = ?")
                values.append(value)

        if set_clauses:
            values.append(1)
            await db.execute(
                f"UPDATE admin_settings SET {', '.join(set_clauses)} WHERE id = ?",
                values
            )
            await db.commit()

        return await get_admin_settings()


# Vault case operations
async def list_vault_cases(user_id: int) -> list[VaultCase]:
    """List cases accessible to user (own private + all public)."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT vc.id, vc.user_id, vc.identifier, vc.name, vc.description,
                      vc.is_public, vc.status, vc.ai_summary, vc.created_at, vc.updated_at,
                      u.username as owner_ip
               FROM vault_cases vc
               JOIN users u ON u.id = vc.user_id
               WHERE vc.user_id = ? OR vc.is_public = 1
               ORDER BY vc.updated_at DESC""",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [VaultCase(**dict(row)) for row in rows]


async def create_vault_case(
    user_id: int, identifier: str, name: str,
    description: str = "", is_public: bool = False,
    owner_ip: str = ""
) -> VaultCase:
    """Create a new vault case."""
    async with get_db() as db:
        now = datetime.utcnow()
        cursor = await db.execute(
            """INSERT INTO vault_cases (user_id, identifier, name, description, is_public, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, identifier, name, description, 1 if is_public else 0, now, now)
        )
        await db.commit()
        return VaultCase(
            id=cursor.lastrowid, user_id=user_id, identifier=identifier,
            name=name, description=description, is_public=is_public,
            status="active", owner_ip=owner_ip, created_at=now, updated_at=now
        )


async def get_vault_case(case_id: int, user_id: int) -> VaultCaseWithRecords | None:
    """Get a case with records if accessible to user."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT vc.id, vc.user_id, vc.identifier, vc.name, vc.description,
                      vc.is_public, vc.status, vc.ai_summary, vc.created_at, vc.updated_at,
                      u.username as owner_ip
               FROM vault_cases vc
               JOIN users u ON u.id = vc.user_id
               WHERE vc.id = ? AND (vc.user_id = ? OR vc.is_public = 1)""",
            (case_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        case = VaultCaseWithRecords(**dict(row))

        cursor = await db.execute(
            """SELECT r.id, r.case_id, r.record_type, r.title, r.content, r.filename,
                      r.original_filename, r.file_size, r.ai_description, r.starred,
                      r.record_date, r.created_by_user_id, r.created_at,
                      COALESCE(cu.username, '') as created_by_ip
               FROM vault_records r
               LEFT JOIN users cu ON cu.id = r.created_by_user_id
               WHERE r.case_id = ?
               ORDER BY r.record_date DESC, r.created_at DESC""",
            (case_id,)
        )
        records = await cursor.fetchall()
        case.records = [VaultRecord(**dict(r)) for r in records]
        case.record_count = len(case.records)
        return case


async def update_vault_case(case_id: int, user_id: int, updates: dict[str, Any]) -> VaultCase | None:
    """Update a case (owner only)."""
    async with get_db() as db:
        set_clauses = ["updated_at = ?"]
        values: list[Any] = [datetime.utcnow()]

        valid_keys = ("identifier", "name", "description", "is_public", "status", "ai_summary")
        for key, value in updates.items():
            if key not in valid_keys or value is None:
                continue
            if key == "is_public":
                set_clauses.append(f"{key} = ?")
                values.append(1 if value else 0)
            else:
                set_clauses.append(f"{key} = ?")
                values.append(value)

        values.extend([case_id, user_id])
        cursor = await db.execute(
            f"UPDATE vault_cases SET {', '.join(set_clauses)} WHERE id = ? AND user_id = ?",
            values
        )
        await db.commit()

        if cursor.rowcount == 0:
            return None

        cursor = await db.execute(
            """SELECT vc.id, vc.user_id, vc.identifier, vc.name, vc.description,
                      vc.is_public, vc.status, vc.ai_summary, vc.created_at, vc.updated_at,
                      u.username as owner_ip
               FROM vault_cases vc
               JOIN users u ON u.id = vc.user_id
               WHERE vc.id = ?""",
            (case_id,)
        )
        row = await cursor.fetchone()
        return VaultCase(**dict(row)) if row else None


async def delete_vault_case(case_id: int, user_id: int) -> bool:
    """Delete a case and all records (owner only)."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM vault_cases WHERE id = ? AND user_id = ?",
            (case_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def search_vault_cases(user_id: int, query: str) -> list[VaultCase]:
    """Search cases by name/identifier for @mention autocomplete (case-insensitive)."""
    async with get_db() as db:
        pattern = f"%{query.lower()}%"
        cursor = await db.execute(
            """SELECT vc.id, vc.user_id, vc.identifier, vc.name, vc.description,
                      vc.is_public, vc.status, vc.ai_summary, vc.created_at, vc.updated_at,
                      u.username as owner_ip
               FROM vault_cases vc
               JOIN users u ON u.id = vc.user_id
               WHERE (vc.user_id = ? OR vc.is_public = 1)
                 AND (LOWER(vc.name) LIKE ? OR LOWER(vc.identifier) LIKE ?)
               ORDER BY vc.updated_at DESC
               LIMIT 20""",
            (user_id, pattern, pattern)
        )
        rows = await cursor.fetchall()
        return [VaultCase(**dict(row)) for row in rows]


# Vault record operations
async def create_vault_record(
    case_id: int, record_type: str, title: str, record_date: str,
    content: str | None = None, filename: str | None = None,
    original_filename: str | None = None, file_size: int | None = None,
    created_by_user_id: int | None = None, created_by_ip: str = ""
) -> VaultRecord:
    """Create a new vault record."""
    async with get_db() as db:
        now = datetime.utcnow()
        cursor = await db.execute(
            """INSERT INTO vault_records
               (case_id, record_type, title, content, filename, original_filename,
                file_size, record_date, created_by_user_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (case_id, record_type, title, content, filename,
             original_filename, file_size, record_date, created_by_user_id, now)
        )
        await db.commit()

        # Touch case updated_at
        await db.execute(
            "UPDATE vault_cases SET updated_at = ? WHERE id = ?",
            (now, case_id)
        )
        await db.commit()

        return VaultRecord(
            id=cursor.lastrowid, case_id=case_id, record_type=record_type,
            title=title, content=content, filename=filename,
            original_filename=original_filename, file_size=file_size,
            ai_description=None, starred=False, record_date=record_date,
            created_by_user_id=created_by_user_id, created_by_ip=created_by_ip,
            created_at=now
        )


async def toggle_vault_record_star(record_id: int) -> VaultRecord | None:
    """Toggle starred status on a record."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT starred FROM vault_records WHERE id = ?",
            (record_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        new_starred = 0 if row["starred"] else 1
        await db.execute(
            "UPDATE vault_records SET starred = ? WHERE id = ?",
            (new_starred, record_id)
        )
        await db.commit()

        cursor = await db.execute(
            """SELECT r.id, r.case_id, r.record_type, r.title, r.content, r.filename,
                      r.original_filename, r.file_size, r.ai_description, r.starred,
                      r.record_date, r.created_by_user_id, r.created_at,
                      COALESCE(cu.username, '') as created_by_ip
               FROM vault_records r
               LEFT JOIN users cu ON cu.id = r.created_by_user_id
               WHERE r.id = ?""",
            (record_id,)
        )
        row = await cursor.fetchone()
        return VaultRecord(**dict(row)) if row else None


async def delete_vault_record(record_id: int) -> bool:
    """Delete a vault record."""
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM vault_records WHERE id = ?",
            (record_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def update_vault_record_ai_description(record_id: int, ai_description: str) -> None:
    """Update AI description for a vault record."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vault_records SET ai_description = ? WHERE id = ?",
            (ai_description, record_id)
        )
        await db.commit()


async def update_vault_case_ai_summary(case_id: int, ai_summary: str) -> None:
    """Update AI summary for a vault case."""
    async with get_db() as db:
        await db.execute(
            "UPDATE vault_cases SET ai_summary = ? WHERE id = ?",
            (ai_summary, case_id)
        )
        await db.commit()


async def get_vault_case_context(case_id: int, user_id: int, max_recent: int = 5) -> str | None:
    """Build context string for @Case injection into chat. Returns None if not accessible."""
    async with get_db() as db:
        # Verify access
        cursor = await db.execute(
            """SELECT id, name, identifier, description, status
               FROM vault_cases
               WHERE id = ? AND (user_id = ? OR is_public = 1)""",
            (case_id, user_id)
        )
        case_row = await cursor.fetchone()
        if not case_row:
            return None

        case = dict(case_row)
        parts = [f'[Referenced Case: "{case["name"]}" ({case["identifier"]}) - {case["status"].title()}]']
        if case["description"]:
            parts.append(f'Description: {case["description"]}')

        # Get starred records
        cursor = await db.execute(
            """SELECT title, content, ai_description, record_type, record_date
               FROM vault_records
               WHERE case_id = ? AND starred = 1
               ORDER BY record_date DESC""",
            (case_id,)
        )
        starred = await cursor.fetchall()

        if starred:
            parts.append("\nStarred Records:")
            for r in starred:
                r = dict(r)
                text = r["content"] or r["ai_description"] or ""
                if text:
                    # Truncate long records
                    text = text[:500] + "..." if len(text) > 500 else text
                parts.append(f'- {r["record_date"]} "{r["title"]}": {text}')

        # Get recent unstarred records
        cursor = await db.execute(
            """SELECT title, content, ai_description, record_type, record_date
               FROM vault_records
               WHERE case_id = ? AND starred = 0
               ORDER BY record_date DESC
               LIMIT ?""",
            (case_id, max_recent)
        )
        recent = await cursor.fetchall()

        if recent:
            parts.append("\nRecent Records:")
            for r in recent:
                r = dict(r)
                text = r["content"] or r["ai_description"] or ""
                if text:
                    text = text[:500] + "..." if len(text) > 500 else text
                label = "[AI Summary] " if r["record_type"] != "text" and r["ai_description"] else ""
                parts.append(f'- {r["record_date"]} "{r["title"]}": {label}{text}')

        parts.append("[End Case Context]")
        return "\n".join(parts)


async def search_vault_records(user_id: int, query: str, case_id: int | None = None) -> list[dict]:
    """Full-text search across vault records accessible to user."""
    async with get_db() as db:
        pattern = f"%{query}%"
        if case_id:
            cursor = await db.execute(
                """SELECT r.id, r.case_id, r.record_type, r.title, r.content,
                          r.ai_description, r.record_date, r.starred,
                          c.name as case_name, c.identifier as case_identifier
                   FROM vault_records r
                   JOIN vault_cases c ON c.id = r.case_id
                   WHERE r.case_id = ? AND (c.user_id = ? OR c.is_public = 1)
                     AND (r.title LIKE ? OR r.content LIKE ? OR r.ai_description LIKE ?)
                   ORDER BY r.record_date DESC
                   LIMIT 50""",
                (case_id, user_id, pattern, pattern, pattern)
            )
        else:
            cursor = await db.execute(
                """SELECT r.id, r.case_id, r.record_type, r.title, r.content,
                          r.ai_description, r.record_date, r.starred,
                          c.name as case_name, c.identifier as case_identifier
                   FROM vault_records r
                   JOIN vault_cases c ON c.id = r.case_id
                   WHERE (c.user_id = ? OR c.is_public = 1)
                     AND (r.title LIKE ? OR r.content LIKE ? OR r.ai_description LIKE ?)
                   ORDER BY r.record_date DESC
                   LIMIT 50""",
                (user_id, pattern, pattern, pattern)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_vault_record(record_id: int) -> VaultRecord | None:
    """Get a single vault record by ID."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT r.id, r.case_id, r.record_type, r.title, r.content, r.filename,
                      r.original_filename, r.file_size, r.ai_description, r.starred,
                      r.record_date, r.created_by_user_id, r.created_at,
                      COALESCE(cu.username, '') as created_by_ip
               FROM vault_records r
               LEFT JOIN users cu ON cu.id = r.created_by_user_id
               WHERE r.id = ?""",
            (record_id,)
        )
        row = await cursor.fetchone()
        return VaultRecord(**dict(row)) if row else None


async def update_vault_record(record_id: int, updates: dict) -> VaultRecord | None:
    """Update a vault record's title and/or content."""
    async with get_db() as db:
        set_clauses = []
        values = []
        for key in ("title", "content"):
            if key in updates and updates[key] is not None:
                set_clauses.append(f"{key} = ?")
                values.append(updates[key])

        if not set_clauses:
            return await get_vault_record(record_id)

        values.append(record_id)
        await db.execute(
            f"UPDATE vault_records SET {', '.join(set_clauses)} WHERE id = ?",
            values
        )
        await db.commit()
        return await get_vault_record(record_id)


# Activity log operations
import logging

_activity_log = logging.getLogger("activity_log")


async def log_activity(user_ip: str, action_type: str, description: str, user_id: int | None = None) -> None:
    """Log a user activity. Fire-and-forget: errors are logged, not raised."""
    try:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO activity_log (user_id, user_ip, action_type, description)
                   VALUES (?, ?, ?, ?)""",
                (user_id, user_ip, action_type, description)
            )
            await db.commit()
    except Exception as e:
        _activity_log.warning(f"Failed to log activity: {e}")


async def get_activity_log(
    offset: int = 0,
    limit: int = 50,
    action_type: str | None = None,
    user_ip: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """Get paginated activity log entries with filters. Returns (entries, total)."""
    async with get_db() as db:
        where_clauses = []
        params: list[Any] = []

        if action_type:
            where_clauses.append("action_type = ?")
            params.append(action_type)
        if user_ip:
            where_clauses.append("user_ip LIKE ?")
            params.append(f"%{user_ip}%")
        if search:
            where_clauses.append("description LIKE ?")
            params.append(f"%{search}%")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Get total count
        cursor = await db.execute(
            f"SELECT COUNT(*) FROM activity_log{where_sql}",
            params
        )
        total = (await cursor.fetchone())[0]

        # Get entries
        cursor = await db.execute(
            f"""SELECT id, user_id, user_ip, action_type, description, created_at
                FROM activity_log{where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset]
        )
        rows = await cursor.fetchall()
        entries = [dict(row) for row in rows]

        return entries, total
