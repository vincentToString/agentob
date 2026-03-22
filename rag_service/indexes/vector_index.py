import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from llama_index.core import Document, StorageContext, Settings, VectorStoreIndex
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.llms.openrouter import OpenRouter

from database import VectorDocument, VectorChunk
from config import settings


class VectorIndexEngine:
    def __init__(self):
        self.chunk_size = settings.kg_chunk_size
        self.chunk_overlap = settings.kg_chunk_overlap

        # Configure LlamaIndex Settings
        # Use default embeddings or None (we'll use our own hash-based embeddings)
        Settings.embed_model = None

        # Configure LLM if API key is available
        if settings.openrouter_api_key:
            Settings.llm = OpenRouter(
                api_key=settings.openrouter_api_key,
                model="deepseek/deepseek-chat-v3.1:free",
                temperature=0.1,
            )
        else:
            # Use a very simple LLM fallback or None
            Settings.llm = None

        # Initialize vector store
        self.vector_store = SimpleVectorStore()
        self.storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )

        # Cache for LlamaIndex indices by document_id
        self._index_cache: Dict[str, VectorStoreIndex] = {}

    async def ingest_document(
        self,
        db: AsyncSession,
        document_id: str,
        content: str,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        start_time = datetime.utcnow()

        # Check if document already exists with eager loading
        result = await db.execute(
            select(VectorDocument)
            .options(selectinload(VectorDocument.chunks))
            .where(VectorDocument.document_id == document_id)
        )
        existing_doc = result.scalar_one_or_none()

        if existing_doc:
            # Update existing document
            existing_doc.content = content
            existing_doc.title = title
            existing_doc.doc_metadata = metadata or {}
            existing_doc.updated_at = datetime.utcnow()

            # Delete old chunks
            for chunk in existing_doc.chunks:
                await db.delete(chunk)
            await db.flush()

            doc = existing_doc
        else:
            # Create new document
            doc = VectorDocument(
                document_id=document_id,
                title=title,
                content=content,
                doc_metadata=metadata or {}
            )
            db.add(doc)

        await db.flush()

        # Create LlamaIndex Document
        llama_doc = Document(
            text=content,
            doc_id=document_id,
            metadata={
                "title": title or "",
                "document_id": document_id,
                **(metadata or {})
            }
        )

        # Build Vector Store Index using LlamaIndex
        # This automatically chunks and creates embeddings
        vector_index = VectorStoreIndex.from_documents(
            [llama_doc],
            storage_context=self.storage_context,
            show_progress=False,
        )

        # Cache the index for this document
        self._index_cache[document_id] = vector_index

        chunks_created = 0

        # Get chunks from the index (LlamaIndex creates nodes which we'll treat as chunks)
        # Access the underlying nodes
        all_nodes = list(vector_index.docstore.docs.values())

        for idx, node in enumerate(all_nodes):
            chunk_id = f"{document_id}_chunk_{idx}"
            chunk_text = node.get_content()

            # Get embedding for this chunk
            embedding_vector = await self._get_embedding(chunk_text)

            # Create chunk record
            chunk = VectorChunk(
                chunk_id=chunk_id,
                document_id=doc.id,
                content=chunk_text,
                chunk_index=idx,
                embedding=embedding_vector
            )
            db.add(chunk)
            await db.flush()
            chunks_created += 1

        await db.commit()

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        return {
            "document_id": document_id,
            "chunks_created": chunks_created,
            "duration_seconds": duration,
            "status": "success"
        }

    async def _get_embedding(self, text: str) -> List[float]:
        # Use hash-based embedding (no external dependencies needed)
        return self._generate_simple_embedding(text)

    def _generate_simple_embedding(self, text: str) -> List[float]:
        import hashlib

        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()

        # Convert to list of floats between -1 and 1
        embedding = []
        for i in range(0, len(hash_bytes), 2):
            val = int.from_bytes(hash_bytes[i:i+2], byteorder='big')
            normalized = (val / 65535.0) * 2 - 1
            embedding.append(normalized)

        # Pad or trim to standard size (384 dimensions)
        target_size = 384
        if len(embedding) < target_size:
            embedding.extend([0.0] * (target_size - len(embedding)))
        else:
            embedding = embedding[:target_size]

        return embedding

    async def query_vector_index(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5
    ) -> Dict[str, Any]:
        # Get query embedding
        query_embedding = await self._get_embedding(query)

        # Search for similar chunks using cosine similarity
        result = await db.execute(
            select(VectorChunk)
            .options(selectinload(VectorChunk.document))
            .limit(top_k * 2)
        )
        chunks = result.scalars().all()

        # Calculate similarity scores
        def cosine_similarity(a, b):
            if not a or not b:
                return 0.0
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(x * x for x in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot_product / (norm_a * norm_b)

        chunk_scores = [
            (chunk, cosine_similarity(query_embedding, chunk.embedding or []))
            for chunk in chunks
        ]
        # Filter for positive similarity scores only
        chunk_scores = [(chunk, score) for chunk, score in chunk_scores if score > 0]
        chunk_scores.sort(key=lambda x: x[1], reverse=True)
        top_chunks = chunk_scores[:top_k]

        results = {
            "query": query,
            "chunks": []
        }

        # Add chunk results
        for chunk, score in top_chunks:
            results["chunks"].append({
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "score": score,
                "document_id": chunk.document.document_id if chunk.document else None,
                "document_title": chunk.document.title if chunk.document else None
            })

        return results

    async def get_document_chunks(
        self,
        db: AsyncSession,
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        # Get document
        result = await db.execute(
            select(VectorDocument).where(VectorDocument.document_id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Get all chunks
        chunk_result = await db.execute(
            select(VectorChunk)
            .where(VectorChunk.document_id == doc.id)
            .order_by(VectorChunk.chunk_index)
        )
        chunks = chunk_result.scalars().all()

        return {
            "document_id": doc.document_id,
            "title": doc.title,
            "metadata": doc.doc_metadata,
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "chunk_index": chunk.chunk_index
                }
                for chunk in chunks
            ],
            "chunks_count": len(chunks)
        }
