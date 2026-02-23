# Quickstart

## Prerequisites

- Docker and Docker Compose.

## Run the full stack

```bash
git clone https://github.com/ragnetic/ragnetic.git
cd ragnetic
docker compose up -d
```

- **Dashboard:** http://localhost:3000  
- **API docs:** http://localhost:8000/docs  
- **Flower (Celery):** http://localhost:5555  

## First steps

1. **Create account / login (required for upload):**
   - Open `http://localhost:3000/login`
   - Register a user, then log in
2. **List knowledge bases:** `GET http://localhost:8000/kb/` with `Authorization: Bearer <token>`.
   - On first register/login, Ragnetic creates a personal KB for that user and grants `owner` role.
3. **Upload a document:** `POST http://localhost:8000/upload/` with bearer token and a file (e.g. PDF, TXT, MD). Optionally pass `?kb_id=1`.
   - Duplicate filename behavior: filenames are unique per knowledge base (case-insensitive). If a filename already exists, upload is blocked.
4. **Check ingestion:** `GET http://localhost:8000/documents/{document_id}/status` with bearer token — wait until `status` is `indexed`.
5. **Manage uploaded docs:** `GET /documents?kb_id=1`, `PATCH /documents/{document_id}` (rename), `DELETE /documents/{document_id}`.
6. **Search:** `GET http://localhost:8000/search/?query=your+query&kb_id=1` with bearer token.
7. **Chat over indexed docs (fast sync):** `POST http://localhost:8000/chat/` with bearer token and JSON body `{"message":"...", "kb_id":1}`.
8. **Chat over indexed docs (stream tokens):** `POST http://localhost:8000/chat/stream` with same JSON body.
9. **Long response lane (async):**
   - Send `POST http://localhost:8000/chat/` with `{"message":"...", "kb_id":1, "async_mode": true}`
   - Poll `GET http://localhost:8000/chat/jobs/{job_id}` until `status=completed`.
10. **Share with team members (owner only):**
   - UI: `http://localhost:3000/members`
   - API: `GET/POST/PATCH/DELETE /kb/{kb_id}/members`

## Local development

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for running the backend and frontend locally against Dockerized Postgres, Redis, Qdrant, and MinIO.

## Next guides

- [Auth and first query](auth-and-first-query.md)
- [Configuration](configuration.md)
- [Troubleshooting](troubleshooting.md)
