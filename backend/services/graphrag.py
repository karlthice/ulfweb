"""GraphRAG service for document processing and querying.

Implements a full RAG pipeline: PDF → chunking → embedding → entity extraction
→ hybrid retrieval (BM25 + vector + entity) → cross-encoder reranking → LLM answer.

Adapted from /home/karlth/src/ragtest/graphrag_auto.py
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import AsyncGenerator

import httpx
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from backend.config import settings
from backend.services import storage

logger = logging.getLogger(__name__)


class GraphRAGService:
    """Service for GraphRAG document processing and querying."""

    _encoder: SentenceTransformer | None = None
    _cross_encoder = None

    def __init__(self, embedding_model: str = "paraphrase-multilingual-mpnet-base-v2"):
        self.embedding_model = embedding_model

    async def get_query_llm_url(self) -> str:
        """Get the LLM URL for document queries from admin settings."""
        admin_settings = await storage.get_admin_settings()
        if admin_settings.document_ai_query_server_id:
            server = await storage.get_server(admin_settings.document_ai_query_server_id)
            if server and server.url:
                return server.url
        return settings.llama.url

    async def get_extraction_llm_url(self) -> str:
        """Get the LLM URL for entity extraction from admin settings."""
        admin_settings = await storage.get_admin_settings()
        if admin_settings.document_ai_extraction_server_id:
            server = await storage.get_server(admin_settings.document_ai_extraction_server_id)
            if server and server.url:
                return server.url
        return settings.llama.url

    async def get_understanding_llm_url(self) -> str:
        """Get the LLM URL for document understanding/summaries from admin settings."""
        admin_settings = await storage.get_admin_settings()
        if admin_settings.document_ai_understanding_server_id:
            server = await storage.get_server(admin_settings.document_ai_understanding_server_id)
            if server and server.url:
                return server.url
        return settings.llama.url

    async def _get_server_parallel_slots(self, role: str) -> int:
        """Get the configured parallel slots for a server role.

        Args:
            role: One of 'extraction', 'understanding', 'query'.

        Returns:
            Number of parallel slots (defaults to 1 if no server configured).
        """
        admin_settings = await storage.get_admin_settings()
        server_id = None
        if role == "extraction":
            server_id = admin_settings.document_ai_extraction_server_id
        elif role == "understanding":
            server_id = admin_settings.document_ai_understanding_server_id
        elif role == "query":
            server_id = admin_settings.document_ai_query_server_id

        if server_id:
            server = await storage.get_server(server_id)
            if server:
                return server.parallel
        return 1

    @classmethod
    def get_encoder(cls, model_name: str = "paraphrase-multilingual-mpnet-base-v2") -> SentenceTransformer:
        """Lazy-load and cache the encoder model."""
        if cls._encoder is None:
            cls._encoder = SentenceTransformer(model_name)
        return cls._encoder

    @classmethod
    def get_cross_encoder(cls):
        """Lazy-load and cache the cross-encoder model for reranking."""
        if cls._cross_encoder is None:
            from sentence_transformers import CrossEncoder
            cls._cross_encoder = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
        return cls._cross_encoder

    def get_content_hash(self, content: bytes) -> str:
        """Generate MD5 hash of content."""
        return hashlib.md5(content).hexdigest()

    async def extract_text_from_pdf(self, pdf_path: Path) -> tuple[list[dict], int]:
        """Extract text from PDF file with per-page tracking.

        Returns:
            (pages, page_count) where pages is a list of
            {"page_number": int, "text": str} dicts.
        """
        reader = PdfReader(pdf_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append({"page_number": i + 1, "text": text})
        return pages, len(reader.pages)

    def chunk_text(self, pages: list[dict], max_chunk_chars: int = 2000,
                   overlap_chars: int = 300) -> list[dict]:
        """Split text into chunks with overlap, preserving paragraph boundaries.

        Uses paragraph boundaries as primary split points, sentences as secondary.
        Tracks page numbers for source attribution.

        Args:
            pages: List of {"page_number": int, "text": str} dicts.
            max_chunk_chars: Target max characters per chunk (~300-500 tokens).
            overlap_chars: Characters to overlap between consecutive chunks.

        Returns:
            List of {"content": str, "page_number": int} dicts.
        """
        # Build paragraphs with page tracking
        paragraphs = []
        for page in pages:
            page_num = page["page_number"]
            # Split by double newlines (paragraph boundaries)
            page_paras = re.split(r'\n\s*\n', page["text"])
            for para in page_paras:
                # Collapse horizontal whitespace but preserve paragraph structure
                para = re.sub(r'[ \t]+', ' ', para).strip()
                if para:
                    paragraphs.append({"text": para, "page_number": page_num})

        if not paragraphs:
            return []

        chunks = []
        current_parts: list[dict] = []
        current_len = 0

        def flush_chunk():
            nonlocal current_parts, current_len
            if not current_parts:
                return
            content = "\n\n".join(p["text"] for p in current_parts)
            page_num = current_parts[0]["page_number"]
            chunks.append({"content": content, "page_number": page_num})
            # Compute overlap: keep trailing paragraphs within overlap budget
            if overlap_chars > 0:
                overlap_parts = []
                overlap_len = 0
                for p in reversed(current_parts):
                    if overlap_len + len(p["text"]) > overlap_chars:
                        break
                    overlap_parts.insert(0, p)
                    overlap_len += len(p["text"])
                current_parts = overlap_parts
                current_len = sum(len(p["text"]) for p in current_parts)
            else:
                current_parts = []
                current_len = 0

        for para in paragraphs:
            para_len = len(para["text"])

            # If a single paragraph exceeds max_chunk_chars, split by sentences
            if para_len > max_chunk_chars:
                flush_chunk()
                sentences = re.split(r'(?<=[.!?])\s+', para["text"])
                for sent in sentences:
                    if current_len + len(sent) > max_chunk_chars and current_parts:
                        flush_chunk()
                    current_parts.append({"text": sent, "page_number": para["page_number"]})
                    current_len += len(sent)
                continue

            if current_len + para_len > max_chunk_chars and current_parts:
                flush_chunk()

            current_parts.append(para)
            current_len += para_len

        # Flush remaining content
        flush_chunk()
        return chunks

    async def call_llm(self, prompt: str, max_tokens: int = 2000,
                       temperature: float = 0.1, llm_url: str | None = None) -> str:
        """Call an LLM endpoint."""
        if llm_url is None:
            llm_url = await self.get_extraction_llm_url()
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    f"{llm_url}/v1/completions",
                    json={
                        "prompt": prompt,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "stop": ["</s>", "```\n\n"]
                    }
                )
                response.raise_for_status()
                return response.json()["choices"][0]["text"].strip()
            except Exception as e:
                print(f"LLM Error: {e}")
                return ""

    async def extract_entities_from_text(self, doc_name: str, text: str,
                                         llm_url: str | None = None) -> tuple[list[dict], list[dict]]:
        """Extract entities and relations from a text segment using LLM.

        No longer truncates input — callers should pass appropriately sized text
        (e.g. individual chunks or small batches).
        """
        prompt = f"""Analyze this document and extract all important entities and relationships.

DOCUMENT: {doc_name}
---
{text}
---

Extract entities and relationships as JSON. Be thorough - capture ALL important concepts, terms, and their relationships.

For each ENTITY include:
- name: the entity name (lowercase, underscores for spaces)
- type: one of [concept, term, person, organization, location, event, rule, component]
- attributes: key facts as key-value pairs

For each RELATION include:
- source: entity name
- relation: one of [relates_to, is_part_of, causes, requires, defines, includes, contrasts_with]
- target: entity name
- evidence: brief quote from text

Output valid JSON only:
```json
{{
  "entities": [
    {{"name": "example", "type": "concept", "attributes": {{"definition": "brief description"}}}}
  ],
  "relations": [
    {{"source": "entity1", "relation": "relates_to", "target": "entity2", "evidence": "quote"}}
  ]
}}
```

JSON:
```json
"""

        response = await self.call_llm(prompt, max_tokens=2000, temperature=0.1,
                                       llm_url=llm_url)

        entities = []
        relations = []

        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group()
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    entity_pattern = r'\{\s*"name":\s*"([^"]+)"[^}]*"type":\s*"([^"]+)"[^}]*"attributes":\s*\{([^}]*)\}'
                    for match in re.finditer(entity_pattern, json_str):
                        name, etype, attrs_str = match.groups()
                        attrs = {}
                        for attr_match in re.finditer(r'"([^"]+)":\s*"([^"]*)"', attrs_str):
                            attrs[attr_match.group(1)] = attr_match.group(2)
                        entities.append({
                            "name": name.lower().replace(" ", "_"),
                            "entity_type": etype,
                            "attributes": attrs
                        })
                    return entities, relations

                for e in data.get("entities", []):
                    entities.append({
                        "name": e.get("name", "unknown").lower().replace(" ", "_"),
                        "entity_type": e.get("type", "unknown"),
                        "attributes": e.get("attributes", {})
                    })

                for r in data.get("relations", []):
                    relations.append({
                        "source": r.get("source", "").lower().replace(" ", "_"),
                        "target": r.get("target", "").lower().replace(" ", "_"),
                        "relation_type": r.get("relation", "related_to"),
                        "evidence": r.get("evidence", "")
                    })

        except Exception as e:
            print(f"Entity extraction error: {e}")

        return entities, relations

    async def extract_entities_from_chunks(self, doc_name: str, chunks: list[dict]) -> tuple[list[dict], list[dict]]:
        """Extract entities and relations by processing chunks in parallel batches.

        Processes chunks in groups of 5, running batches in parallel up to
        the configured server parallel slot limit. Deduplicates entities
        across batches.
        """
        batch_size = 5
        batches = []
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_text = "\n\n---\n\n".join(c["content"] for c in batch)
            batches.append(batch_text)

        if not batches:
            return [], []

        # Resolve URL and parallelism once before the gather
        extraction_url = await self.get_extraction_llm_url()
        max_parallel = await self._get_server_parallel_slots("extraction")
        semaphore = asyncio.Semaphore(max_parallel)
        total = len(batches)
        completed = [0]
        start_time = time.monotonic()

        async def process_batch(batch_idx: int, text: str):
            async with semaphore:
                entities, relations = await self.extract_entities_from_text(
                    doc_name, text, llm_url=extraction_url
                )
                completed[0] += 1
                elapsed = time.monotonic() - start_time
                rate = completed[0] / elapsed if elapsed > 0 else 0
                remaining = (total - completed[0]) / rate if rate > 0 else 0
                logger.info(
                    "Entity extraction: batch %d/%d done (%.1f batches/min, ETA %.0fs)",
                    completed[0], total, rate * 60, remaining
                )
                return entities, relations

        results = await asyncio.gather(*(
            process_batch(i, text) for i, text in enumerate(batches)
        ))

        all_entities = []
        all_relations = []
        for entities, relations in results:
            all_entities.extend(entities)
            all_relations.extend(relations)

        # Deduplicate entities by name, merging attributes
        seen: dict[str, int] = {}
        unique_entities = []
        for entity in all_entities:
            name = entity["name"]
            if name in seen:
                existing = unique_entities[seen[name]]
                existing["attributes"].update(entity.get("attributes", {}))
            else:
                seen[name] = len(unique_entities)
                unique_entities.append(entity)

        # Deduplicate relations
        seen_rels: set[tuple] = set()
        unique_relations = []
        for rel in all_relations:
            key = (rel["source"], rel["relation_type"], rel["target"])
            if key not in seen_rels:
                seen_rels.add(key)
                unique_relations.append(rel)

        return unique_entities, unique_relations

    async def generate_chunk_context(self, doc_name: str, doc_summary: str,
                                     chunk_content: str,
                                     llm_url: str | None = None) -> str:
        """Generate a contextual prefix for a chunk using the understanding LLM.

        Implements Anthropic's Contextual Retrieval technique: prepends a short
        context summary to each chunk before embedding, reducing retrieval
        failures by 35-67%.
        """
        if llm_url is None:
            llm_url = await self.get_understanding_llm_url()
        prompt = f"""Document: {doc_name}
Document summary: {doc_summary}

Here is a chunk from this document:
---
{chunk_content[:1500]}
---

Write a brief context sentence (under 100 tokens) that situates this chunk within the document. Include the document topic, section, and any key entities mentioned. Do not repeat the chunk content. Write in the SAME LANGUAGE as the chunk text.

Context:"""

        response = await self.call_llm(prompt, max_tokens=150, temperature=0.1,
                                       llm_url=llm_url)
        context = response.strip().split('\n')[0].strip()
        if len(context) > 500:
            context = context[:500]
        return context

    async def generate_document_summary(self, doc_name: str, pages: list[dict]) -> str:
        """Generate a brief summary of the document for contextual retrieval."""
        llm_url = await self.get_understanding_llm_url()
        sample_text = pages[0]["text"][:1500] if pages else ""
        if len(pages) > 1:
            sample_text += "\n...\n" + pages[-1]["text"][:1000]

        prompt = f"""Document: {doc_name}

{sample_text}

Write a 2-3 sentence summary of what this document is about. Write in the SAME LANGUAGE as the document text.

Summary:"""

        return await self.call_llm(prompt, max_tokens=200, temperature=0.1,
                                   llm_url=llm_url)

    async def process_document(self, document_id: int, pdf_path: Path) -> None:
        """Process a PDF document: extract text, chunk, extract entities, generate embeddings.

        Pipeline:
        1. Extract text with page tracking
        2. Chunk with overlap and paragraph preservation
        3. Generate contextual prefixes (Contextual Retrieval)
        4. Embed chunks (with context prefix prepended)
        5. Extract entities per-chunk-batch (not truncated)
        6. Link entities to chunks (with underscore fix)
        """
        doc = await storage.get_document(document_id)
        if not doc:
            return

        await storage.update_document_status(document_id, "processing")

        try:
            pipeline_start = time.monotonic()
            pages, page_count = await self.extract_text_from_pdf(pdf_path)
            await storage.update_document_status(document_id, "processing",
                                                 page_count=page_count)

            chunks = self.chunk_text(pages)
            logger.info("Document %d: %d pages, %d chunks", document_id, page_count, len(chunks))

            # Check if contextual retrieval should be skipped
            admin_settings = await storage.get_admin_settings()
            if admin_settings.skip_contextual_retrieval:
                logger.info("Skipping contextual retrieval (disabled in admin settings)")
                for chunk in chunks:
                    chunk["context_prefix"] = ""
            else:
                # Contextual retrieval: generate context prefix for each chunk in parallel
                try:
                    doc_summary = await self.generate_document_summary(
                        doc.original_filename, pages
                    )

                    # Resolve URL and parallelism once before the gather
                    understanding_url = await self.get_understanding_llm_url()
                    max_parallel = await self._get_server_parallel_slots("understanding")
                    semaphore = asyncio.Semaphore(max_parallel)
                    total = len(chunks)
                    completed = [0]
                    start_time = time.monotonic()

                    async def generate_context_for_chunk(idx: int, chunk: dict):
                        async with semaphore:
                            try:
                                context = await self.generate_chunk_context(
                                    doc.original_filename, doc_summary,
                                    chunk["content"], llm_url=understanding_url
                                )
                            except Exception:
                                context = ""
                            completed[0] += 1
                            elapsed = time.monotonic() - start_time
                            rate = completed[0] / elapsed if elapsed > 0 else 0
                            remaining = (total - completed[0]) / rate if rate > 0 else 0
                            logger.info(
                                "Chunk context: %d/%d done (%.1f chunks/min, ETA %.0fs)",
                                completed[0], total, rate * 60, remaining
                            )
                            return idx, context

                    results = await asyncio.gather(*(
                        generate_context_for_chunk(i, chunk)
                        for i, chunk in enumerate(chunks)
                    ))

                    for idx, context in results:
                        chunks[idx]["context_prefix"] = context

                except Exception:
                    # If summary generation fails, skip contextual retrieval
                    logger.warning("Document summary generation failed, skipping contextual retrieval")
                    for chunk in chunks:
                        chunk["context_prefix"] = ""

            # Embed chunks with context prefix prepended for better retrieval
            logger.info("Document %d: embedding %d chunks", document_id, len(chunks))
            encoder = self.get_encoder(self.embedding_model)
            chunk_texts_for_embedding = [
                f"{c.get('context_prefix', '')} {c['content']}" if c.get('context_prefix')
                else c["content"]
                for c in chunks
            ]
            if chunk_texts_for_embedding:
                chunk_embeddings = encoder.encode(chunk_texts_for_embedding)
                for i, chunk in enumerate(chunks):
                    chunk["embedding"] = chunk_embeddings[i].tobytes()

            await storage.bulk_insert_chunks(document_id, chunks)

            stored_chunks = await storage.get_chunks_by_document(document_id)
            chunk_id_map = {c["chunk_index"]: c["id"] for c in stored_chunks}

            # Extract entities per-chunk-batch in parallel
            logger.info("Document %d: extracting entities from %d chunks", document_id, len(chunks))
            entities, relations = await self.extract_entities_from_chunks(
                doc.original_filename, chunks
            )
            logger.info("Document %d: found %d entities, %d relations",
                        document_id, len(entities), len(relations))

            entity_name_to_id = {}
            if entities:
                entity_embeddings = encoder.encode([
                    f"{e['name'].replace('_', ' ')} {' '.join(f'{k}:{v}' for k,v in e.get('attributes', {}).items())}"
                    for e in entities
                ])
                for i, entity in enumerate(entities):
                    entity["embedding"] = entity_embeddings[i].tobytes()

                entity_ids = await storage.bulk_insert_entities(
                    doc.collection_id, document_id, entities
                )

                for i, entity in enumerate(entities):
                    entity_name_to_id[entity["name"]] = entity_ids[i]

                    # Fix: replace underscores with spaces for matching (Issue #8)
                    entity_match_name = entity["name"].replace("_", " ").lower()
                    # Skip overly broad short entity names
                    if len(entity_match_name) < 4:
                        continue

                    linked_chunk_ids = []
                    for chunk_idx, chunk in enumerate(chunks):
                        if entity_match_name in chunk["content"].lower():
                            if chunk_idx in chunk_id_map:
                                linked_chunk_ids.append(chunk_id_map[chunk_idx])

                    if linked_chunk_ids:
                        await storage.link_entity_to_chunks(entity_ids[i], linked_chunk_ids)

            if relations:
                valid_relations = []
                for rel in relations:
                    src_id = entity_name_to_id.get(rel["source"])
                    tgt_id = entity_name_to_id.get(rel["target"])
                    if src_id and tgt_id:
                        valid_relations.append({
                            "source_entity_id": src_id,
                            "target_entity_id": tgt_id,
                            "relation_type": rel["relation_type"],
                            "evidence": rel.get("evidence")
                        })

                if valid_relations:
                    await storage.bulk_insert_relations(doc.collection_id, valid_relations)

            elapsed = time.monotonic() - pipeline_start
            logger.info("Document %d: processing complete in %.1fs", document_id, elapsed)
            await storage.update_document_status(document_id, "ready",
                                                 page_count=page_count)

        except Exception as e:
            await storage.update_document_status(document_id, "error",
                                                 error_message=str(e))
            raise

    async def query(self, collection_id: int, question: str,
                    top_k: int = 10) -> AsyncGenerator[dict, None]:
        """Query a collection using hybrid search with RRF and cross-encoder reranking.

        Pipeline:
        1. Compute query embedding
        2. Score via entity similarity (ranking list 1)
        3. Score via vector similarity (ranking list 2)
        4. Score via BM25 keyword search (ranking list 3)
        5. Fuse rankings with Reciprocal Rank Fusion (RRF)
        6. Rerank top candidates with cross-encoder
        7. Build prompt with improved structure and stream LLM answer
        """
        encoder = self.get_encoder(self.embedding_model)
        query_emb = encoder.encode([question])[0]

        entities = await storage.get_entities_by_collection(collection_id)
        chunks = await storage.get_chunks_by_collection(collection_id)
        relations = await storage.get_relations_by_collection(collection_id)

        if not entities and not chunks:
            yield {"type": "error", "content": "No documents in this collection"}
            return

        # --- Ranking list 1: Entity similarity ---
        entity_ranked_chunks: dict[int, float] = {}
        relevant_entities = []
        if entities:
            entity_scores = []
            for entity in entities:
                if entity.get("embedding"):
                    emb = np.frombuffer(entity["embedding"], dtype=np.float32)
                    sim = float(np.dot(query_emb, emb) / (
                        np.linalg.norm(query_emb) * np.linalg.norm(emb) + 1e-8
                    ))
                    entity_scores.append((entity, sim))

            entity_scores.sort(key=lambda x: x[1], reverse=True)
            relevant_entities = entity_scores[:top_k]

            for entity, score in relevant_entities:
                entity_chunk_ids = await storage.get_chunks_for_entity(entity["id"])
                for chunk_id in entity_chunk_ids:
                    entity_ranked_chunks[chunk_id] = max(
                        entity_ranked_chunks.get(chunk_id, 0.0), score
                    )

        # --- Ranking list 2: Vector similarity ---
        vector_ranked_chunks: dict[int, float] = {}
        if chunks:
            chunk_emb_list = []
            chunk_id_list = []
            for chunk in chunks:
                if chunk.get("embedding"):
                    emb = np.frombuffer(chunk["embedding"], dtype=np.float32)
                    chunk_emb_list.append(emb)
                    chunk_id_list.append(chunk["id"])

            if chunk_emb_list:
                emb_matrix = np.array(chunk_emb_list)
                # Batch cosine similarity using numpy
                norms = np.linalg.norm(emb_matrix, axis=1)
                query_norm = np.linalg.norm(query_emb)
                sims = emb_matrix @ query_emb / (norms * query_norm + 1e-8)
                for i, sim in enumerate(sims):
                    vector_ranked_chunks[chunk_id_list[i]] = float(sim)

        # --- Ranking list 3: BM25 keyword search ---
        bm25_ranked_chunks: dict[int, float] = {}
        bm25_results = await storage.search_chunks_fts(collection_id, question)
        for chunk_id, bm25_score in bm25_results:
            bm25_ranked_chunks[chunk_id] = bm25_score

        # --- Reciprocal Rank Fusion (replaces magic weights) ---
        RRF_K = 60
        all_chunk_ids = set(entity_ranked_chunks) | set(vector_ranked_chunks) | set(bm25_ranked_chunks)

        # Build ranked lists sorted by score descending
        entity_rank = {cid: rank for rank, (cid, _) in enumerate(
            sorted(entity_ranked_chunks.items(), key=lambda x: x[1], reverse=True)
        )}
        vector_rank = {cid: rank for rank, (cid, _) in enumerate(
            sorted(vector_ranked_chunks.items(), key=lambda x: x[1], reverse=True)
        )}
        bm25_rank = {cid: rank for rank, (cid, _) in enumerate(
            sorted(bm25_ranked_chunks.items(), key=lambda x: x[1], reverse=True)
        )}

        rrf_scores: dict[int, float] = {}
        for cid in all_chunk_ids:
            score = 0.0
            if cid in entity_rank:
                score += 1.0 / (RRF_K + entity_rank[cid])
            if cid in vector_rank:
                score += 1.0 / (RRF_K + vector_rank[cid])
            if cid in bm25_rank:
                score += 1.0 / (RRF_K + bm25_rank[cid])
            rrf_scores[cid] = score

        logger.info(
            "Query '%s': RRF fusion - %d entity, %d vector, %d BM25 candidates -> %d unique chunks",
            question[:50], len(entity_ranked_chunks), len(vector_ranked_chunks),
            len(bm25_ranked_chunks), len(all_chunk_ids)
        )

        # Get top candidates for reranking
        rerank_count = min(20, len(rrf_scores))
        sorted_by_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        candidate_ids = [cid for cid, _ in sorted_by_rrf[:rerank_count]]

        chunk_map = {c["id"]: c for c in chunks}
        candidate_chunks = [chunk_map[cid] for cid in candidate_ids if cid in chunk_map]

        # --- Cross-encoder reranking ---
        # Only rerank when we have enough candidates beyond top_k to benefit
        if len(candidate_chunks) >= top_k + 5:
            try:
                cross_enc = self.get_cross_encoder()
                pairs = [[question, c["content"]] for c in candidate_chunks]
                ce_scores = cross_enc.predict(pairs)
                scored = list(zip(candidate_chunks, ce_scores))
                scored.sort(key=lambda x: float(x[1]), reverse=True)
                relevant_chunks = [c for c, _ in scored[:top_k]]
            except Exception:
                # Fallback if cross-encoder unavailable
                relevant_chunks = candidate_chunks[:top_k]
        else:
            relevant_chunks = candidate_chunks[:top_k]

        logger.info(
            "Query '%s': selected %d chunks (from %d candidates, top_k=%d)",
            question[:50], len(relevant_chunks), len(candidate_chunks), top_k
        )
        for i, c in enumerate(relevant_chunks):
            preview = c["content"][:100].replace("\n", " ")
            logger.info("  Chunk %d [%s p.%s]: %s...",
                        i + 1, c.get("original_filename", "?"),
                        c.get("page_number", "?"), preview)

        # Build entity context (supplementary)
        entity_context_lines = []
        for entity, score in relevant_entities:
            name = entity.get("name", "unknown").replace("_", " ")
            etype = entity.get("entity_type", "")
            source = entity.get("original_filename", "")
            attrs = entity.get("attributes", {})
            attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items()) if attrs else "no attributes"
            entity_context_lines.append(f"- {name} [{source}] ({etype}): {attr_str}")

            for rel in relations:
                if rel["source_entity_id"] == entity["id"]:
                    target_name = rel.get("target_name", "").replace("_", " ")
                    entity_context_lines.append(
                        f"    -> {rel['relation_type']} -> {target_name}"
                    )

        entity_context = "\n".join(entity_context_lines)

        # Build chunk context with source attribution
        chunk_context_parts = []
        for i, c in enumerate(relevant_chunks, 1):
            filename = c.get("original_filename", "document")
            page = c.get("page_number")
            source_label = filename + (f", p.{page}" if page else "")
            chunk_context_parts.append(f"[Source {i}: {source_label}]\n{c['content']}")

        chunk_context = "\n\n".join(chunk_context_parts)

        sources = list(set(
            c.get("original_filename", "document") for c in relevant_chunks
        ))

        # Improved prompt structure: question first, source text prominent,
        # entities as supplementary context, multilingual support
        prompt = f"""You are a helpful assistant that answers questions using ONLY the provided source text. The source text may be in any language.

Question: {question}

SOURCE TEXT:
{chunk_context if chunk_context else "No relevant text found."}

SUPPLEMENTARY FACTS (from knowledge graph):
{entity_context if entity_context else "None."}

Instructions:
- Answer based ONLY on the source text above
- Answer in the same language as the question
- Cite sources using [Source N] notation when possible
- Only say you cannot answer if the source text is truly unrelated to the question
- Be thorough but concise

Answer:"""

        llm_url = await self.get_query_llm_url()
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    f"{llm_url}/v1/completions",
                    json={
                        "prompt": prompt,
                        "max_tokens": 1024,
                        "temperature": 0.3,
                        "stream": True,
                        "stop": ["</s>", "\n\nQuestion:", "\n\nAnswer:", "---"]
                    }
                )
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            parsed = json.loads(data)
                            text = parsed.get("choices", [{}])[0].get("text", "")
                            if text:
                                yield {"type": "content", "content": text}
                        except json.JSONDecodeError:
                            continue

                yield {"type": "sources", "content": "", "sources": sources}
                yield {"type": "done", "content": ""}

            except Exception as e:
                yield {"type": "error", "content": str(e)}


graphrag_service = GraphRAGService()
