# Ragnetic

**Open-Source RAG Knowledge Base Platform**

Ragnetic is a self-hosted Retrieval-Augmented Generation (RAG) platform for teams that want private document chat and search with full control over infrastructure and data.

## Features

- **Single-command full stack** — Docker Compose for backend, frontend, and all dependencies
- **Access control** — Authenticated, knowledge-base–scoped roles (owner / editor / viewer)
- **Async ingestion** — PDF, TXT, MD, DOCX with status tracking and duplicate-filename handling
- **Document lifecycle** — List, rename, delete, replace-on-reupload per knowledge base
- **Hybrid retrieval** — Dense vectors + BM25 + RRF, with optional cross-encoder reranking
- **RAG chat** — Answers with source snippets, citations, and session history; sync, streaming, and async long-response modes
- **Local-first LLM** — Ollama by default with optional OpenAI fallback

## Quickstart

### Prerequisites

- Docker and Docker Compose

### Run locally

1. **Clone and start services**
   ```bash
   git clone https://github.com/ragnetic/ragnetic.git
   cd ragnetic
   docker compose up -d
   ```

2. **Optional: pull a local model for chat**
   ```bash
   docker compose exec ollama ollama run llama3.2
   ```

3. **Open**
   - **Dashboard:** [http://localhost:3000](http://localhost:3000)
   - **API docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Celery Flower:** [http://localhost:5555](http://localhost:5555)

For step-by-step auth, upload, search, and chat, see [Auth and first query](docs/guides/auth-and-first-query.md).

## Architecture

See [Visual architecture](docs/architecture/diagram.md) and [Technical stack](docs/architecture/tech-stack.md).

| Layer        | Technology                          |
|-------------|-------------------------------------|
| Frontend    | Next.js, React, Tailwind CSS v4     |
| Backend     | Python 3.11+, FastAPI, Celery       |
| Data        | PostgreSQL, Qdrant, Redis, MinIO    |
| LLM         | Ollama (default), OpenAI fallback   |

## Contributing and community

- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

## Documentation

- [Documentation index](docs/README.md)
- [Quickstart](docs/guides/quickstart.md)
- [Configuration](docs/guides/configuration.md)
- [Troubleshooting](docs/guides/troubleshooting.md)
- [API endpoints](docs/reference/api-endpoints.md)

## License

Licensed under [Apache 2.0](LICENSE).
