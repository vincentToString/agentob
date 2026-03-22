from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class DocumentIngestRequest(BaseModel):
    document_id: str = Field(..., description="Unique document identifier")
    content: str = Field(..., description="Raw document content")
    title: Optional[str] = Field(None, description="Document title")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class DocumentIngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    entities_created: int
    relations_created: int
    duration_seconds: float
    status: str


class QueryRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return")
    include_relations: bool = Field(True, description="Include related entities")


class ChunkResult(BaseModel):
    chunk_id: str
    content: str
    score: float
    document_id: Optional[str]


class EntityResult(BaseModel):
    entity_id: str
    text: str
    type: str
    metadata: Dict[str, Any]


class RelationResult(BaseModel):
    relation_id: str
    source: Optional[str]
    target: Optional[str]
    type: str
    confidence: float


class QueryResponse(BaseModel):
    query: str
    chunks: List[ChunkResult]
    entities: List[EntityResult]
    relations: List[RelationResult]


class DocumentGraphResponse(BaseModel):
    document_id: str
    title: Optional[str]
    metadata: Dict[str, Any]
    entities: List[Dict[str, Any]]
    relations: List[Dict[str, Any]]
    chunks_count: int


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    service: str


# Vector Index Schemas

class VectorIngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    duration_seconds: float
    status: str


class VectorQueryRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return")


class VectorChunkResult(BaseModel):
    chunk_id: str
    content: str
    score: float
    document_id: Optional[str]
    document_title: Optional[str]


class VectorQueryResponse(BaseModel):
    query: str
    chunks: List[VectorChunkResult]


class VectorDocumentResponse(BaseModel):
    document_id: str
    title: Optional[str]
    metadata: Dict[str, Any]
    chunks: List[Dict[str, Any]]
    chunks_count: int
