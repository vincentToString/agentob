import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from llama_index.core import Document, StorageContext, Settings
from llama_index.core.indices.knowledge_graph import KnowledgeGraphIndex
from llama_index.core.graph_stores import SimpleGraphStore
from llama_index.llms.openrouter import OpenRouter

from database import KGDocument, KGChunk, KGEntity, KGRelation
from config import settings


class KnowledgeGraphIndexEngine:
    def __init__(self):
        self.chunk_size = settings.kg_chunk_size
        self.chunk_overlap = settings.kg_chunk_overlap
        self.max_triplets = settings.kg_max_entities_per_chunk

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

        # Initialize graph store
        self.graph_store = SimpleGraphStore()
        self.storage_context = StorageContext.from_defaults(
            graph_store=self.graph_store
        )

        # Cache for LlamaIndex indices by document_id
        self._index_cache: Dict[str, KnowledgeGraphIndex] = {}

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
            select(KGDocument)
            .options(selectinload(KGDocument.chunks))
            .where(KGDocument.document_id == document_id)
        )
        existing_doc = result.scalar_one_or_none()

        if existing_doc:
            # Update existing document
            existing_doc.content = content
            existing_doc.title = title
            existing_doc.doc_metadata = metadata or {}
            existing_doc.updated_at = datetime.utcnow()

            # Delete old chunks (cascade will delete entities and relations)
            for chunk in existing_doc.chunks:
                await db.delete(chunk)
            await db.flush()

            doc = existing_doc
        else:
            # Create new document
            doc = KGDocument(
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

        # Build Knowledge Graph Index using LlamaIndex
        # This automatically extracts entities and relations
        kg_index = KnowledgeGraphIndex.from_documents(
            [llama_doc],
            max_triplets_per_chunk=self.max_triplets,
            storage_context=self.storage_context,
            show_progress=False,
        )

        # Cache the index for this document
        self._index_cache[document_id] = kg_index

        # Extract triplets from the graph store and save to PostgreSQL
        # For SimpleGraphStore, we'll use the rel_map which stores all relationships
        triplets = []
        if hasattr(self.graph_store, '_data') and hasattr(self.graph_store._data, 'rel_map'):
            # rel_map is a dict of subject -> list of (object, relation_type)
            for subj, relations in self.graph_store._data.rel_map.items():
                for obj, rel_type in relations:
                    triplets.append((subj, rel_type, obj))

        total_entities = 0
        total_relations = 0
        chunks_created = 0
        entity_map = {}  # Map entity text to entity object

        # Get chunks from the index (LlamaIndex creates nodes which we'll treat as chunks)
        # Access the underlying nodes
        all_nodes = list(kg_index.docstore.docs.values())

        for idx, node in enumerate(all_nodes):
            chunk_id = f"{document_id}_chunk_{idx}"
            chunk_text = node.get_content()

            # Get embedding for this chunk
            embedding_vector = await self._get_embedding(chunk_text)

            # Create chunk record
            chunk = KGChunk(
                chunk_id=chunk_id,
                document_id=doc.id,
                content=chunk_text,
                chunk_index=idx,
                embedding=embedding_vector
            )
            db.add(chunk)
            await db.flush()
            chunks_created += 1

            # Extract entities and relations for this chunk from triplets
            # Filter triplets that came from this chunk
            chunk_triplets = [
                t for t in triplets
                if self._is_triplet_from_text(t, chunk_text)
            ]

            for triplet in chunk_triplets:
                subj, rel, obj = triplet

                # Create entities
                for entity_text, entity_type in [(subj, "ENTITY"), (obj, "ENTITY")]:
                    entity_key = entity_text.lower()

                    if entity_key not in entity_map:
                        entity = KGEntity(
                            entity_id=str(uuid.uuid4()),
                            chunk_id=chunk.id,
                            entity_text=entity_text,
                            entity_type=entity_type,
                            entity_metadata={}
                        )
                        db.add(entity)
                        await db.flush()

                        entity_map[entity_key] = entity
                        total_entities += 1

                # Create relation
                source_entity = entity_map.get(subj.lower())
                target_entity = entity_map.get(obj.lower())

                if source_entity and target_entity:
                    relation = KGRelation(
                        relation_id=str(uuid.uuid4()),
                        source_entity_id=source_entity.id,
                        target_entity_id=target_entity.id,
                        relation_type=rel.upper(),
                        confidence=0.9,  # LlamaIndex extracted relations have high confidence
                        relation_metadata={}
                    )
                    db.add(relation)
                    total_relations += 1

        await db.commit()

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        return {
            "document_id": document_id,
            "chunks_created": chunks_created,
            "entities_created": total_entities,
            "relations_created": total_relations,
            "duration_seconds": duration,
            "status": "success"
        }

    def _is_triplet_from_text(self, triplet: tuple, text: str) -> bool:
        subj, rel, obj = triplet
        text_lower = text.lower()
        return (
            subj.lower() in text_lower or
            obj.lower() in text_lower
        )

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

    async def query_knowledge_graph(
        self,
        db: AsyncSession,
        query: str,
        top_k: int = 5,
        include_relations: bool = True
    ) -> Dict[str, Any]:
        # Get query embedding
        query_embedding = await self._get_embedding(query)

        # Search for similar chunks using cosine similarity
        result = await db.execute(
            select(KGChunk)
            .options(selectinload(KGChunk.document))
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
        chunk_scores.sort(key=lambda x: x[1], reverse=True)
        top_chunks = chunk_scores[:top_k]

        # Search entities by text matching
        entity_result = await db.execute(
            select(KGEntity).where(
                KGEntity.entity_text.ilike(f"%{query}%")
            ).limit(top_k)
        )
        matched_entities = entity_result.scalars().all()

        results = {
            "query": query,
            "chunks": [],
            "entities": [],
            "relations": []
        }

        # Add chunk results
        for chunk, score in top_chunks:
            results["chunks"].append({
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "score": score,
                "document_id": chunk.document.document_id if chunk.document else None
            })

        # Add entity results
        entity_ids = []
        for entity in matched_entities:
            results["entities"].append({
                "entity_id": entity.entity_id,
                "text": entity.entity_text,
                "type": entity.entity_type,
                "metadata": entity.entity_metadata
            })
            entity_ids.append(entity.id)

        # Add relations if requested
        if include_relations and entity_ids:
            relation_result = await db.execute(
                select(KGRelation).where(
                    or_(
                        KGRelation.source_entity_id.in_(entity_ids),
                        KGRelation.target_entity_id.in_(entity_ids)
                    )
                )
            )
            relations = relation_result.scalars().all()

            for relation in relations:
                results["relations"].append({
                    "relation_id": relation.relation_id,
                    "source": relation.source_entity.entity_text if relation.source_entity else None,
                    "target": relation.target_entity.entity_text if relation.target_entity else None,
                    "type": relation.relation_type,
                    "confidence": relation.confidence
                })

        return results

    async def get_document_graph(
        self,
        db: AsyncSession,
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        # Get document
        result = await db.execute(
            select(KGDocument).where(KGDocument.document_id == document_id)
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Get all chunks
        chunk_result = await db.execute(
            select(KGChunk).where(KGChunk.document_id == doc.id)
        )
        chunks = chunk_result.scalars().all()

        # Get all entities from chunks
        chunk_ids = [chunk.id for chunk in chunks]
        entity_result = await db.execute(
            select(KGEntity).where(KGEntity.chunk_id.in_(chunk_ids))
        )
        entities = entity_result.scalars().all()

        # Get all relations
        entity_ids = [entity.id for entity in entities]
        if entity_ids:
            relation_result = await db.execute(
                select(KGRelation).where(
                    or_(
                        KGRelation.source_entity_id.in_(entity_ids),
                        KGRelation.target_entity_id.in_(entity_ids)
                    )
                )
            )
            relations = relation_result.scalars().all()
        else:
            relations = []

        return {
            "document_id": doc.document_id,
            "title": doc.title,
            "metadata": doc.doc_metadata,
            "entities": [
                {
                    "entity_id": e.entity_id,
                    "text": e.entity_text,
                    "type": e.entity_type
                }
                for e in entities
            ],
            "relations": [
                {
                    "source": r.source_entity.entity_text if r.source_entity else None,
                    "target": r.target_entity.entity_text if r.target_entity else None,
                    "type": r.relation_type,
                    "confidence": r.confidence
                }
                for r in relations
            ],
            "chunks_count": len(chunks)
        }
