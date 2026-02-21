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

Fix:
- Confirm Ollama container is running.
- Pull a local model once:

```bash
docker exec -it ragnetic-ollama ollama run llama3.2
```

- Or configure `OPENAI_API_KEY` for cloud fallback.

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
