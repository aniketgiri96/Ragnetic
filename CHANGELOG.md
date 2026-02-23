# Changelog

All notable changes to Ragnetic are documented here. Versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Docs
- Open-source readiness pass: full Apache-2.0 license text, new `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`, and GitHub issue/PR templates.
- Updated `README.md` and `CONTRIBUTING.md` to remove placeholders and document runnable setup/validation commands.
- Aligned architecture, configuration, and API docs with current implementation details (endpoint paths, response behavior, and default settings).
- Added `.github/workflows/ci.yml` to run backend tests and frontend build on pull requests and pushes to `main`.

### UI change
- Frontend: Tailwind CSS (v4) with base theme; sticky nav with logo and links; home page hero and feature cards; card-based forms and styled inputs/buttons on Upload, Search, Chat, and Login; chat message bubbles and source blocks; responsive layout and focus states.

### Minor change
- RAG chat: `POST /chat/` accepts JSON body `{ message, kb_id?, session_id? }`; runs retrieval over KB, builds context, calls LLM (Ollama or OpenAI), returns `{ answer, sources }`.
- Chat architecture: added streaming endpoint `POST /chat/stream` (SSE token events), async long-response jobs (`ChatJob` model + Celery worker task), and polling endpoint `GET /chat/jobs/{job_id}`.
- Streaming chat now emits public reasoning/progress events (`reasoning`, `sources_preview`, `heartbeat`) so UI can show live answer evolution without exposing hidden chain-of-thought.
- Document management: uploads now support replace-on-duplicate filename (`replace_existing=true`), stale chunks are removed on re-index, and new document APIs/UI support list, rename, and delete.
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
- Chat reliability: increased default `LLM_TIMEOUT_SECONDS` to `90`, added Ollama timeout retry with reduced `num_predict`, and changed fallback output to be strictly extractive (no speculative synthesis).

---

## [0.1.0] - 2026-02-20

### Minor change
- Initial scaffold: Docker Compose (PostgreSQL, Qdrant, Redis, Celery, Flower, MinIO, backend, frontend).
- Stub API: `POST /upload/`, `GET /search/`, `POST /chat/` with in-memory behavior.
- README and CONTRIBUTING added.
