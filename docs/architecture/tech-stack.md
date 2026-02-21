# Technical Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Frontend | Next.js 14, TypeScript, TailwindCSS, Shadcn UI | SSR, type safety, polished components |
| State | Zustand + TanStack Query | Global state and server-state caching |
| Backend API | FastAPI (Python 3.11+) | Async, Pydantic, OpenAPI, strong performance |
| Task queue | Celery + Redis | Distributed tasks; Redis for cache and pub/sub |
| Primary DB | PostgreSQL 15 | ACID, user/KB metadata, audit logs |
| Vector store | Qdrant | Purpose-built vectors; self-hosted; hybrid support |
| Embeddings | sentence-transformers (local) / OpenAI (optional) | Default: all-MiniLM-L6-v2; configurable per KB |
| LLM | Ollama (local) / OpenAI / Anthropic | Local-first; cloud optional |
| Search (BM25) | Elasticsearch (optional) / BM25Okapi (embedded) | Embedded for simple deploys; ES for scale |
| Object storage | Local filesystem / S3-compatible (MinIO) | Abstracted behind a single interface |

All services are run via a single `docker-compose up` for a full stack.
