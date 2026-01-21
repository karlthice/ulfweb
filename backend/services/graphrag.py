"""GraphRAG service for document processing and querying.

Adapted from /home/karlth/src/ragtest/graphrag_auto.py
"""

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import AsyncGenerator

import httpx
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from backend.config import settings
from backend.services import storage


class GraphRAGService:
    """Service for GraphRAG document processing and querying."""

    _encoder: SentenceTransformer | None = None

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

    @classmethod
    def get_encoder(cls, model_name: str = "paraphrase-multilingual-mpnet-base-v2") -> SentenceTransformer:
        """Lazy-load and cache the encoder model."""
        if cls._encoder is None:
            cls._encoder = SentenceTransformer(model_name)
        return cls._encoder

    def get_content_hash(self, content: bytes) -> str:
        """Generate MD5 hash of content."""
        return hashlib.md5(content).hexdigest()

    async def extract_text_from_pdf(self, pdf_path: Path) -> tuple[str, int]:
        """Extract text from PDF file, returns (text, page_count)."""
        reader = PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages), len(reader.pages)

    def chunk_text(self, text: str, max_chunk_size: int = 400) -> list[dict]:
        """Split text into chunks."""
        chunks = []
        text = re.sub(r'\s+', ' ', text).strip()
        sentences = re.split(r'(?<=[.!?])\s+', text)

        current = ""
        for sent in sentences:
            if len(current) + len(sent) < max_chunk_size:
                current += sent + " "
            else:
                if current.strip():
                    chunks.append({"content": current.strip()})
                current = sent + " "

        if current.strip():
            chunks.append({"content": current.strip()})

        return chunks

    async def call_llm(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.1) -> str:
        """Call the LLM for entity extraction."""
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

    async def extract_entities_from_text(self, doc_name: str, text: str) -> tuple[list[dict], list[dict]]:
        """Extract entities and relations from document text using LLM."""
        if len(text) > 4000:
            text = text[:2500] + "\n...[truncated]...\n" + text[-1500:]

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

        response = await self.call_llm(prompt, max_tokens=2000, temperature=0.1)

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

    async def process_document(self, document_id: int, pdf_path: Path) -> None:
        """Process a PDF document: extract text, chunk, extract entities, generate embeddings."""
        doc = await storage.get_document(document_id)
        if not doc:
            return

        await storage.update_document_status(document_id, "processing")

        try:
            text, page_count = await self.extract_text_from_pdf(pdf_path)
            await storage.update_document_status(document_id, "processing", page_count=page_count)

            chunks = self.chunk_text(text)

            encoder = self.get_encoder(self.embedding_model)
            chunk_texts = [c["content"] for c in chunks]
            if chunk_texts:
                chunk_embeddings = encoder.encode(chunk_texts)
                for i, chunk in enumerate(chunks):
                    chunk["embedding"] = chunk_embeddings[i].tobytes()

            await storage.bulk_insert_chunks(document_id, chunks)

            stored_chunks = await storage.get_chunks_by_document(document_id)
            chunk_id_map = {c["chunk_index"]: c["id"] for c in stored_chunks}

            entities, relations = await self.extract_entities_from_text(
                doc.original_filename, text
            )

            entity_name_to_id = {}
            if entities:
                entity_embeddings = encoder.encode([
                    f"{e['name']} {' '.join(f'{k}:{v}' for k,v in e.get('attributes', {}).items())}"
                    for e in entities
                ])
                for i, entity in enumerate(entities):
                    entity["embedding"] = entity_embeddings[i].tobytes()

                entity_ids = await storage.bulk_insert_entities(
                    doc.collection_id, document_id, entities
                )

                for i, entity in enumerate(entities):
                    entity_name_to_id[entity["name"]] = entity_ids[i]

                    linked_chunk_ids = []
                    entity_name_lower = entity["name"].lower()
                    for chunk_idx, chunk in enumerate(chunks):
                        if entity_name_lower in chunk["content"].lower():
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

            await storage.update_document_status(document_id, "ready", page_count=page_count)

        except Exception as e:
            await storage.update_document_status(document_id, "error", error_message=str(e))
            raise

    async def query(self, collection_id: int, question: str, top_k: int = 5) -> AsyncGenerator[dict, None]:
        """Query a collection using GraphRAG and stream the response."""
        encoder = self.get_encoder(self.embedding_model)
        query_emb = encoder.encode([question])[0]

        entities = await storage.get_entities_by_collection(collection_id)
        chunks = await storage.get_chunks_by_collection(collection_id)
        relations = await storage.get_relations_by_collection(collection_id)

        if not entities and not chunks:
            yield {"type": "error", "content": "No documents in this collection"}
            return

        relevant_entities = []
        if entities:
            entity_scores = []
            for entity in entities:
                if entity.get("embedding"):
                    emb = np.frombuffer(entity["embedding"], dtype=np.float32)
                    sim = cosine_similarity([query_emb], [emb])[0][0]
                    entity_scores.append((entity, sim))

            entity_scores.sort(key=lambda x: x[1], reverse=True)
            relevant_entities = entity_scores[:top_k]

        entity_context_lines = []
        for entity, score in relevant_entities:
            name = entity.get("name", "unknown")
            etype = entity.get("entity_type", "")
            source = entity.get("original_filename", "")
            attrs = entity.get("attributes", {})
            attr_str = ", ".join(f"{k}={v}" for k, v in attrs.items()) if attrs else "no attributes"
            entity_context_lines.append(f"- {name} [{source}] ({etype}): {attr_str}")

            for rel in relations:
                if rel["source_entity_id"] == entity["id"]:
                    entity_context_lines.append(f"    -> {rel['relation_type']} -> {rel['target_name']}")

        entity_context = "\n".join(entity_context_lines)

        chunk_scores = defaultdict(float)

        for entity, score in relevant_entities:
            entity_chunk_ids = await storage.get_chunks_for_entity(entity["id"])
            for chunk_id in entity_chunk_ids:
                chunk_scores[chunk_id] += score

        if chunks:
            chunk_emb_matrix = []
            chunk_id_list = []
            for chunk in chunks:
                if chunk.get("embedding"):
                    emb = np.frombuffer(chunk["embedding"], dtype=np.float32)
                    chunk_emb_matrix.append(emb)
                    chunk_id_list.append(chunk["id"])

            if chunk_emb_matrix:
                sims = cosine_similarity([query_emb], chunk_emb_matrix)[0]
                for i, sim in enumerate(sims):
                    chunk_scores[chunk_id_list[i]] += sim * 0.5

        sorted_chunks = sorted(chunk_scores.items(), key=lambda x: x[1], reverse=True)
        top_chunk_ids = [cid for cid, _ in sorted_chunks[:top_k]]

        chunk_map = {c["id"]: c for c in chunks}
        relevant_chunks = [chunk_map[cid] for cid in top_chunk_ids if cid in chunk_map]

        chunk_context = "\n\n".join(
            f"[{c.get('original_filename', 'document')}]: {c['content']}"
            for c in relevant_chunks
        )

        sources = list(set(c.get("original_filename", "document") for c in relevant_chunks))

        prompt = f"""Answer the question using the knowledge graph facts and source text below.

KNOWLEDGE GRAPH FACTS:
{entity_context if entity_context else "No specific entities found."}

SOURCE TEXT:
{chunk_context if chunk_context else "No relevant text found."}

IMPORTANT: Use the available information to give an accurate answer. Be concise.

Question: {question}

Answer:"""

        llm_url = await self.get_query_llm_url()
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    f"{llm_url}/v1/completions",
                    json={
                        "prompt": prompt,
                        "max_tokens": 250,
                        "temperature": 0.3,
                        "stream": True
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
