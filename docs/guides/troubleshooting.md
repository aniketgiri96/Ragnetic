# Troubleshooting

## Upload returns `401 Not authenticated`

Cause: `/upload/` requires a bearer token.

Fix:
- Log in at `http://localhost:3000/login`, then retry upload.
- For API calls, pass `Authorization: Bearer <token>`.

## Document status stays `processing`

Cause: Celery worker is not running, cannot access storage, or failed during parse/embed.

Check:

```bash
docker ps
```

Expected containers include `ragnetic-celery-worker`, `ragnetic-redis`, and `ragnetic-backend`.

Inspect worker logs:

```bash
docker logs ragnetic-celery-worker --tail 200
```

## Chat returns LLM error

Common message: `Ensure Ollama is running or set OPENAI_API_KEY`.

Fix checklist:
1. Confirm Ollama container is running:

```bash
docker compose ps ollama
```

2. Verify Ollama is reachable from host and backend:

```bash
curl -sS http://localhost:11434/api/tags
docker compose exec -T backend curl -sS http://ollama:11434/api/tags
```

3. Pull a local model once if missing:

```bash
docker exec -it ragnetic-ollama ollama pull llama3.2
```

4. Validate generation latency directly against Ollama:

```bash
time curl -sS http://localhost:11434/api/generate -d '{"model":"llama3.2","prompt":"Say hi in one sentence.","stream":false}'
```

5. Validate backend model config:

```bash
docker compose exec -T backend env | grep -E 'OLLAMA_URL|OLLAMA_MODEL|OPENAI_API_KEY'
```

6. If config changed, restart backend + worker:

```bash
docker compose restart backend celery_worker
```

7. If local Ollama is still unavailable, configure `OPENAI_API_KEY` for cloud fallback.

## Long generations exceed sync request time

If answer generation is long, treat it as an architecture routing concern, not just a timeout tweak.

Use these request lanes:

- Interactive lane: `POST /chat/stream` for token streaming (SSE).
- Background lane: `POST /chat/` with `"async_mode": true` and poll `GET /chat/jobs/{job_id}`.
- Short lane: `POST /chat/` for normal fast responses.

Operational checks for async lane:

```bash
docker compose ps celery_worker
docker compose logs celery_worker --tail 200
```

The worker log should include `app.tasks.chat.process_chat_job`.

## Search returns empty results

Possible causes:
- Query KB ID does not match uploaded document KB.
- Document is not yet `indexed`.
- Parser extracted little/no text from file.

Check document status first, then retry with simpler keyword queries.

## Backend starts but DB objects are missing

Cause: startup race during DB initialization.

Fix:
- Ensure Postgres is healthy (`ragnetic-db` container).
- Restart backend after DB is ready:

```bash
docker restart ragnetic-backend
```

## CORS errors in frontend

Cause: frontend URL not allowed by backend CORS config.

Current allowed origins are:
- `http://localhost:3000`
- `http://frontend:3000`

If you run frontend from another host/port, update CORS settings in `backend/app/main.py`.
