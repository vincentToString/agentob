# RAG Service

A smart document indexing service that turns your documents into searchable knowledge graphs. Built with FastAPI and LlamaIndex.

## What It Does

Throw a document at it, and it will:
- Break it into chunks
- Extract entities and relationships (using LLMs)
- Store everything in PostgreSQL
- Let you search semantically or by relationships

## Quick Start

### Using Docker (Recommended)

```bash
# Start the service
docker-compose up -d rag_service

# Check it's running
curl http://localhost:8002/health

# View logs
docker logs -f rag_service
```

That's it. The service runs on port 8002.

### Local Development

```bash
# Install dependencies (uses uv for speed)
./setup.sh

# Or manually
uv sync
source .venv/bin/activate
python main.py
```

## How to Use

### 1. Index a Document

```bash
curl -X POST http://localhost:8002/api/v1/vector-index/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "my-doc",
    "content": "Your document text here...",
    "title": "My Doc",
    "metadata": {"author": "me"}
  }'
```

### 2. Search

```bash
curl -X POST http://localhost:8002/api/v1/vector-index/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "what is this about?",
    "top_k": 5
  }'
```

### 3. Explore

Open http://localhost:8002/docs for the full API playground.

## Two Indexing Modes

### Vector Index (Fast & Simple)
- Pure semantic search
- Great for general Q&A
- Endpoint: `/api/v1/vector-index/*`

### Knowledge Graph Index (Smart & Detailed)
- Extracts entities and relationships
- Better for complex queries
- Endpoint: `/api/v1/kg-index/*`

Use whichever fits your needs. Vector is faster, KG is smarter.

## Configuration

Set these environment variables (or use `.env`):

```bash
# Database
POSTGRES_HOST=localhost
POSTGRES_USER=prowl_user
POSTGRES_PASSWORD=prowl_password
POSTGRES_DB=prowl_db

# LLM (for entity extraction)
OPENROUTER_API_KEY=your-key-here
OPENROUTER_BASE=https://openrouter.ai/api/v1

# Optional tuning
KG_CHUNK_SIZE=512           # Text chunk size
KG_CHUNK_OVERLAP=50         # Overlap between chunks
KG_MAX_ENTITIES_PER_CHUNK=10  # Max entities per chunk
```

## From Python Code

```python
import httpx

# Index a document
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8002/api/v1/vector-index/ingest",
        json={
            "document_id": "doc-123",
            "content": "Your text here",
            "title": "My Document"
        }
    )
    print(response.json())

# Query it
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8002/api/v1/vector-index/query",
        json={"query": "tell me about X", "top_k": 3}
    )
    results = response.json()
    for chunk in results['chunks']:
        print(f"Score: {chunk['score']}")
        print(f"Text: {chunk['content']}\n")
```

## Architecture

```
Document
   ↓
Chunking (512 tokens, 50 overlap)
   ↓
Embedding (hash-based by default)
   ↓
PostgreSQL Storage
   ↓
   ├─ Vector Index (chunks + embeddings)
   └─ Knowledge Graph (entities + relations)
```

## Database Tables

- `vector_documents` / `vector_chunks` - Vector index
- `kg_documents` / `kg_chunks` - Knowledge graph chunks
- `kg_entities` - Extracted entities
- `kg_relations` - Relationships between entities

All async-ready with SQLAlchemy.

## Dependencies

Managed with [uv](https://github.com/astral-sh/uv) (super fast Rust-based package manager):
- FastAPI + Uvicorn
- LlamaIndex (core + OpenRouter)
- SQLAlchemy + asyncpg
- PostgreSQL client libraries

See [pyproject.toml](pyproject.toml) for the full list.

## API Endpoints

### Health
- `GET /health` - Check if service is alive

### Vector Index
- `POST /api/v1/vector-index/ingest` - Add document
- `POST /api/v1/vector-index/query` - Search documents
- `GET /api/v1/vector-index/document/{id}` - Get document

### Knowledge Graph
- `POST /api/v1/kg-index/ingest` - Add document (with entity extraction)
- `POST /api/v1/kg-index/query` - Search with entities/relations
- `GET /api/v1/kg-index/document/{id}` - Get document graph

Full docs at http://localhost:8002/docs when running.

## Development

```bash
# Install uv (if needed)
pip install uv

# Setup
uv sync

# Run tests (TODO)
uv run pytest

# Format code
uv run ruff format .

# Add dependency
uv add package-name

# Update lock file
uv lock --upgrade
```

## Docker Build

The Dockerfile uses uv for blazing-fast dependency installation:
- Old way (pip): ~60 seconds
- New way (uv): ~4 seconds

```dockerfile
# Install deps with uv
RUN uv sync --frozen

# Installs 84 packages in milliseconds
```

## Troubleshooting

**Service won't start?**
- Check PostgreSQL is running: `docker ps | grep postgres`
- Check logs: `docker logs rag_service`

**Slow queries?**
- Reduce `top_k` parameter
- Increase `KG_CHUNK_SIZE` (fewer chunks)

**No entities extracted?**
- Make sure `OPENROUTER_API_KEY` is set
- Check the model is available

## What's Next

This is v0.1. Future improvements:
- [ ] Redis caching
- [ ] Batch ingestion
- [ ] Document updates/deletion
- [ ] Graph analytics
- [ ] Multi-modal support (PDFs, images)

## Contributing

Standard flow:
1. Create feature branch
2. Make changes
3. Run tests (when we have them)
4. Open PR

Keep it simple, keep it fast.

---

Built for [PROwl](../) - AI-powered PR reviews.
