# Technical Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Frontend | Next.js + React (JavaScript), Tailwind CSS v4 | Browser UI for login, upload, search, chat, and member management |
| Backend API | FastAPI (Python 3.11+) | HTTP API, auth, RBAC, ingestion orchestration |
| Task queue | Celery + Redis | Asynchronous ingestion processing |
| Primary DB | PostgreSQL 15 | Users, knowledge bases, memberships, documents, chat sessions/messages |
| Vector store | Qdrant | Dense vector indexing and search |
| Sparse retrieval | In-process BM25 over bounded corpus snapshot | Lexical matching without extra service dependency |
| Fusion and rerank | RRF + optional cross-encoder | Blends dense/sparse ranking; rerank available when enabled |
| Object storage | MinIO (S3-compatible) | File storage for uploaded documents |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) with deterministic fallback | Local embeddings when dependency is installed |
| LLM | Ollama (default) with optional OpenAI fallback | Local-first runtime, cloud fallback if configured |

All services can be run with `docker compose up -d` for a full local stack.
