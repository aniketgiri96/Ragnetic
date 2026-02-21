# Ragnetic

**Open-Source RAG Knowledge Base Platform**

Ragnetic is a self-hosted, enterprise-ready Retrieval-Augmented Generation (RAG) platform. It allows organizations to deploy a private, controllable AI system that reasons over proprietary data in minutes, without vendor lock-in or leaking data to third-party cloud APIs.

## Features

- **5-Minute Deployment**: Spin up the entire stack using a single `docker-compose up` command.
- **Semantic-Aware Chunking**: Intelligently chunks documents respecting structural integrity and semantic topic boundaries.
- **Hybrid Retrieval & Reranking**: Combines dense vector search (Qdrant) and sparse search (BM25) with cross-encoder reranking for maximum accuracy.
- **Grounded Generation**: Minimized hallucinations through strict citation-enforced prompting. Every answer includes exact source highlights.
- **Multi-Tenancy & Access Control**: Built-in Knowledge Base-Scoped Role-Based Access Control (RBAC). 
- **Reliable Async Ingestion**: Celery-powered document processing with progress tracking.
- **Local First**: Built-in support for running LLMs and embedding models locally using Ollama and `sentence-transformers`.

## Quickstart

### Prerequisites
- Docker and Docker Compose installed.

### Run Locally
1. Clone the repository:
   ```bash
   git clone https://github.com/ragnetic/ragnetic.git
   cd ragnetic
   ```
2. Start the services:
   ```bash
   docker-compose up -d
   ```
3. (Optional) Pull an Ollama model for RAG Chat. After the stack is up, run:
   ```bash
   docker exec -it ragnetic-ollama ollama run llama3.2
   ```
   Exit the model prompt with `/bye`. Chat will use this model; you can change `OLLAMA_MODEL` in `docker-compose.yml` and pull a different model (e.g. `ollama run mistral`).
4. Access the Ragnetic Dashboard:
   Navigate to [http://localhost:3000](http://localhost:3000)

5. Access the Backend API Docs:
   Navigate to [http://localhost:8000/docs](http://localhost:8000/docs)

## Architecture

High-level view of what you're building:

See [Visual architecture](docs/architecture/diagram.md) for system and flow diagrams.

Ragnetic uses a modern, scalable stack:
- **Frontend**: Next.js 14, TailwindCSS, Shadcn UI
- **Backend**: Python 3.11+, FastAPI, Celery
- **Database**: PostgreSQL 15 (User Auth, Metadata)
- **Vector Database**: Qdrant (Embeddings)
- **Task Broker/Cache**: Redis
- **Embedding Models**: `sentence-transformers`
- **LLM Support**: Ollama (Local), OpenAI/Anthropic (Cloud)

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to get started, our development workflow, and coding standards.

## Documentation

- [Documentation index](docs/README.md)
- [Docs quickstart](docs/guides/quickstart.md)
- [Vision and goals](docs/vision-and-goals.md)
- [Product overview](docs/product-overview.md) · [Personas](docs/personas.md)
- [Market and competitors](docs/market-and-competitors.md)
- [Architecture](docs/architecture/tech-stack.md) · [Data flows](docs/architecture/data-flows.md) · [Visual diagram](docs/architecture/diagram.md)
- [Guides: auth and first query](docs/guides/auth-and-first-query.md) · [Configuration](docs/guides/configuration.md) · [Troubleshooting](docs/guides/troubleshooting.md)
- [Reference: API endpoints](docs/reference/api-endpoints.md) · [Hardware and models](docs/reference/hardware-and-models.md)

## License

This project is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.
