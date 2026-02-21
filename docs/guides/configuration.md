# Configuration Guide

Ragnetic backend settings are read from environment variables (see `backend/app/core/config.py`).

## Core variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql://ragnetic:ragneticpassword@localhost:5432/ragnetic` | Postgres connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis cache / queue base URL |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `CELERY_BROKER_URL` | falls back to `REDIS_URL` | Celery broker |
| `CELERY_RESULT_BACKEND` | `REDIS_URL` with DB 1 | Celery result backend |
| `MINIO_URL` | `http://localhost:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | `admin` | MinIO access key |
| `MINIO_SECRET_KEY` | `password` | MinIO secret key |
| `MINIO_BUCKET` | `ragnetic` | Bucket name for uploads |

## Auth and security

| Variable | Default | Purpose |
|----------|---------|---------|
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRE_HOURS` | `24` | Token lifetime |
| `ENVIRONMENT` | `development` | Set to `production` to enforce secure JWT secret check at startup |

For production, always set a strong unique `JWT_SECRET`. Startup now fails in `production` when `JWT_SECRET` remains default.

## LLM settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `llama3.2` | Default local chat model |
| `OPENAI_API_KEY` | empty | Optional OpenAI fallback |

## Retrieval settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `RETRIEVAL_TOP_K` | `5` | Number of chunks returned for search/chat context |
| `RETRIEVAL_DENSE_LIMIT` | `30` | Dense vector candidates pulled from Qdrant |
| `RETRIEVAL_SPARSE_POOL` | `800` | Max points scanned for lexical BM25 scoring |
| `RETRIEVAL_RERANK_TOP_N` | `12` | Number of fused candidates passed to optional cross-encoder rerank |

## Frontend variable

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Frontend API base URL |

## Docker Compose defaults

`docker-compose.yml` already wires service-to-service URLs for local deployment. If you change ports/hosts, update both:

1. Backend environment values in `docker-compose.yml`.
2. Frontend `NEXT_PUBLIC_API_URL` in `docker-compose.yml` (or local env).

## Production notes

- Replace all default credentials (`POSTGRES_PASSWORD`, MinIO keys, JWT secret).
- Do not expose internal services publicly unless required (`redis`, `qdrant`, `db`).
- Run behind a reverse proxy with TLS.
- Pin model versions and keep embedding model consistent between indexing and querying.
