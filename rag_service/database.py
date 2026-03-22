from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Index, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import settings

Base = declarative_base()


class KGDocument(Base):
    __tablename__ = "kg_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(512))
    content = Column(Text, nullable=False)
    doc_metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    chunks = relationship("KGChunk", back_populates="document", cascade="all, delete-orphan")


class KGChunk(Base):
    __tablename__ = "kg_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(255), unique=True, nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("kg_documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(JSON)  # Store as JSON array for pgvector compatibility
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("KGDocument", back_populates="chunks")
    entities = relationship("KGEntity", back_populates="chunk", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_chunk_document", "document_id", "chunk_index"),
    )


class KGEntity(Base):
    __tablename__ = "kg_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(String(255), unique=True, nullable=False, index=True)
    chunk_id = Column(Integer, ForeignKey("kg_chunks.id", ondelete="CASCADE"), nullable=False)
    entity_text = Column(String(512), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    chunk = relationship("KGChunk", back_populates="entities")
    outgoing_relations = relationship(
        "KGRelation",
        foreign_keys="KGRelation.source_entity_id",
        back_populates="source_entity",
        cascade="all, delete-orphan"
    )
    incoming_relations = relationship(
        "KGRelation",
        foreign_keys="KGRelation.target_entity_id",
        back_populates="target_entity",
        cascade="all, delete-orphan"
    )


class KGRelation(Base):
    __tablename__ = "kg_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    relation_id = Column(String(255), unique=True, nullable=False, index=True)
    source_entity_id = Column(Integer, ForeignKey("kg_entities.id", ondelete="CASCADE"), nullable=False)
    target_entity_id = Column(Integer, ForeignKey("kg_entities.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(100), nullable=False, index=True)
    confidence = Column(Float, default=1.0)
    relation_metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    source_entity = relationship(
        "KGEntity",
        foreign_keys=[source_entity_id],
        back_populates="outgoing_relations"
    )
    target_entity = relationship(
        "KGEntity",
        foreign_keys=[target_entity_id],
        back_populates="incoming_relations"
    )

    __table_args__ = (
        Index("idx_relation_source_target", "source_entity_id", "target_entity_id"),
        Index("idx_relation_type", "relation_type"),
    )


class VectorDocument(Base):
    __tablename__ = "vector_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(512))
    content = Column(Text, nullable=False)
    doc_metadata = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    chunks = relationship("VectorChunk", back_populates="document", cascade="all, delete-orphan")


class VectorChunk(Base):
    __tablename__ = "vector_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chunk_id = Column(String(255), unique=True, nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("vector_documents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(JSON)  # Store as JSON array for pgvector compatibility
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("VectorDocument", back_populates="chunks")

    __table_args__ = (
        Index("idx_vector_chunk_document", "document_id", "chunk_index"),
    )


# Async engine and session
engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
