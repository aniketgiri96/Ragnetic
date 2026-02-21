# Quickstart

## Prerequisites

- Docker and Docker Compose.

## Run the full stack

```bash
git clone https://github.com/knowai/knowai.git
cd knowai
docker-compose up -d
```

- **Dashboard:** http://localhost:3000  
- **API docs:** http://localhost:8000/docs  
- **Flower (Celery):** http://localhost:5555  

## First steps

1. **List knowledge bases:** `GET http://localhost:8000/kb/` — returns the default KB.
2. **Upload a document:** `POST http://localhost:8000/upload/` with a file (e.g. PDF, TXT, MD). Optionally pass `?kb_id=1`.
3. **Check ingestion:** `GET http://localhost:8000/documents/{document_id}/status` — wait until `status` is `indexed`.
4. **Search:** `GET http://localhost:8000/search/?query=your+query&kb_id=1`.

## Local development

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for running the backend and frontend locally against Dockerized Postgres, Redis, Qdrant, and MinIO.
