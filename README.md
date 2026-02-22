# Ragnetic

**Open-Source RAG Knowledge Base Platform**

Ragnetic is a self-hosted Retrieval-Augmented Generation (RAG) platform for
teams that want private document chat and search with control over infrastructure.

## Features

- Single-command full stack with Docker Compose
- Authenticated, knowledge-base scoped access control (owner/editor/viewer)
- Async ingestion pipeline (PDF, TXT, MD, DOCX) with status tracking
- Hybrid retrieval (dense + BM25 + RRF) with optional cross-encoder reranking
- RAG chat responses with source snippets and session history
- Local-first LLM support via Ollama with optional OpenAI fallback

## Quickstart

### Prerequisites

- Docker and Docker Compose plugin

### Run locally

1. Clone:
   ```bash
   git clone https://github.com/ragnetic/ragnetic.git
   cd ragnetic
   ```
2. Start services:
   ```bash
   docker compose up -d
   ```
3. Optional: pull a local Ollama model for chat:
   ```bash
   docker exec -it ragnetic-ollama ollama run llama3.2
   ```
4. Open:
   - Dashboard: [http://localhost:3000](http://localhost:3000)
   - API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

For step-by-step auth/upload/search/chat calls, use
[Auth and first query](docs/guides/auth-and-first-query.md).

## Architecture

See [Visual architecture](docs/architecture/diagram.md) and
[Technical stack](docs/architecture/tech-stack.md).

Core stack:

- Frontend: Next.js + React + Tailwind CSS
- Backend: Python 3.11+, FastAPI, Celery
- Data: PostgreSQL, Qdrant, Redis, MinIO
- LLM: Ollama (default), OpenAI fallback

## Contributing and Community

- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Support channels: [SUPPORT.md](SUPPORT.md)

## Documentation

- [Documentation index](docs/README.md)
- [Quickstart](docs/guides/quickstart.md)
- [Configuration](docs/guides/configuration.md)
- [Troubleshooting](docs/guides/troubleshooting.md)
- [API endpoints](docs/reference/api-endpoints.md)

## License

Licensed under [Apache 2.0](LICENSE).
