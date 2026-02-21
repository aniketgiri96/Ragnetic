# Changelog

All notable changes to Ragnetic are documented here. Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### UI change
- Frontend: Tailwind CSS (v4) with base theme; sticky nav with logo and links; home page hero and feature cards; card-based forms and styled inputs/buttons on Upload, Search, Chat, and Login; chat message bubbles and source blocks; responsive layout and focus states.

### Minor change
- RAG chat: `POST /chat/` accepts JSON body `{ message, kb_id?, session_id? }`; runs retrieval over KB, builds context, calls LLM (Ollama or OpenAI), returns `{ answer, sources }`.
- LLM adapter in `app/services/llm.py` (Ollama default; optional OpenAI when `OPENAI_API_KEY` set). Config: `ollama_url`, `ollama_model`.
- Frontend: Upload, Search, and Chat pages with KB selector; API client in `lib/api.js`; nav and global CSS.
- Auth: User model, `POST /auth/register` and `POST /auth/login` (JWT); upload endpoint protected; frontend login page and token in API client.
- Backend restructured into `app` package for Docker Compose compatibility.
- Celery ingestion pipeline: parse (PDF, TXT, MD, DOCX), chunk, embed, index to Qdrant; status tracking.
- Knowledge bases and documents in PostgreSQL; MinIO for file storage; Qdrant for vectors.
- New API: `GET /kb/`, `GET /documents/{id}/status`; upload and search support optional `kb_id`.
- Documentation: vision, market, product overview, personas, architecture (tech stack, data flows, ingestion, retrieval), reference (hardware and models).

### Fix
- Docker Compose backend and Celery worker entrypoints now use `app.main:app` and `app.core.celery_app`.

---

## [0.1.0] - 2026-02-20

### Minor change
- Initial scaffold: Docker Compose (PostgreSQL, Qdrant, Redis, Celery, Flower, MinIO, backend, frontend).
- Stub API: `POST /upload/`, `GET /search/`, `POST /chat/` with in-memory behavior.
- README and CONTRIBUTING added.
