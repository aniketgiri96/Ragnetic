# API Endpoints Reference

Base URL (local): `http://localhost:8000`

Interactive OpenAPI docs: `/docs`

## Auth

### `POST /auth/register`
Create a new user account.

Rate limit: 10 requests/minute per IP+email.

Request body:

```json
{
  "email": "you@example.com",
  "password": "your-password"
}
```

Success response:

```json
{
  "message": "Registered"
}
```

### `POST /auth/login`
Log in and receive a bearer token.

Rate limit: 20 requests/minute per IP+email.

Request body:

```json
{
  "email": "you@example.com",
  "password": "your-password"
}
```

Success response:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

## Knowledge Bases

### `GET /kb/`
List knowledge bases accessible to the current user.

Auth: `Authorization: Bearer <token>` required.

Success response:

```json
[
  {
    "id": 1,
    "name": "Priya KB",
    "description": "Personal knowledge base for priya@example.com",
    "role": "owner"
  }
]
```

## KB Members (Sharing / RBAC)

### `GET /kb/{kb_id}/members`
List members for a knowledge base.

Auth: `Authorization: Bearer <token>` required.  
Permission: `viewer` or higher on the KB.

Success response:

```json
[
  {
    "kb_id": 1,
    "user_id": 7,
    "email": "owner@example.com",
    "role": "owner",
    "created_at": "2026-02-21T07:14:33.606515"
  }
]
```

### `POST /kb/{kb_id}/members`
Add a user to a KB by email (or update their role if already present).

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

Request body:

```json
{
  "email": "teammate@example.com",
  "role": "editor"
}
```

### `PATCH /kb/{kb_id}/members/{member_user_id}`
Update an existing member role.

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

Request body:

```json
{
  "role": "viewer"
}
```

### `DELETE /kb/{kb_id}/members/{member_user_id}`
Remove a member from a KB.

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

Constraint: last owner cannot be removed.

## Documents

### `POST /upload/`
Upload a document and enqueue ingestion.

Auth: `Authorization: Bearer <token>` required.
Rate limit: 30 requests/minute per user+IP.

Query params:
- `kb_id` (optional): target knowledge base ID

Form-data:
- `file`: PDF, TXT, MD, or DOCX

Success response:

```json
{
  "filename": "employee-handbook.pdf",
  "status": "queued",
  "document_id": 12
}
```

If identical content already exists in the same knowledge base, upload returns the existing `document_id` and includes `deduplicated: true`:

```json
{
  "filename": "employee-handbook.pdf",
  "status": "queued",
  "document_id": 12,
  "deduplicated": true,
  "message": "Identical content already queued/indexed in this knowledge base."
}
```

### `GET /documents/{document_id}/status`
Get ingestion status for a document.

Auth: `Authorization: Bearer <token>` required.

Success response:

```json
{
  "document_id": 12,
  "filename": "employee-handbook.pdf",
  "status": "indexed",
  "error_message": null
}
```

Possible statuses: `pending`, `processing`, `indexed`, `failed`.

## Retrieval

### `GET /search/`
Run semantic search over a knowledge base.

Auth: `Authorization: Bearer <token>` required.
Rate limit: 120 requests/minute per user+IP.

Query params:
- `query` (required)
- `kb_id` (optional, defaults to first knowledge base)

Success response:

```json
[
  {
    "snippet": "...",
    "score": 0.812,
    "dense_score": 0.742,
    "sparse_score": 1.992,
    "metadata": {
      "source": "employee-handbook.pdf",
      "doc_id": 12
    }
  }
]
```

## Chat (RAG)

### `POST /chat/`
Ask a question and receive an answer grounded in retrieved document chunks.

Response mode: non-streaming JSON.

Auth: `Authorization: Bearer <token>` required.
Rate limit: 90 requests/minute per user+IP.

Request body:

```json
{
  "message": "What is our PTO policy?",
  "kb_id": 1,
  "session_id": "optional-session-id",
  "async_mode": false
}
```

Success response:

```json
{
  "answer": "...",
  "session_id": "b4ce5b2fca0147ff8b952f5f703d1a1a",
  "sources": [
    {
      "snippet": "...",
      "score": 0.812,
      "metadata": {
        "source": "employee-handbook.pdf",
        "doc_id": 12
      }
    }
  ]
}
```

`session_id` is optional in request, but recommended. If omitted, server creates a new session ID and returns it.

If `async_mode=true` (or server heuristics classify the prompt as long-running), response is queued:

```json
{
  "mode": "async",
  "status": "queued",
  "job_id": "9bc6c3ea6dc149aeb8492444b91f7482",
  "session_id": "optional-session-id"
}
```

### `POST /chat/stream`
Stream chat tokens using Server-Sent Events (SSE).

Auth: `Authorization: Bearer <token>` required.
Rate limit: 90 requests/minute per user+IP.

Request body is the same as `POST /chat/` (except `async_mode` is ignored).

Event stream:
- `event: meta` with `session_id`
- `event: reasoning` with public pipeline steps (`understand`, `retrieve`, `evidence`, `draft`, `evolve`, `finalize`, etc.)
- `event: sources_preview` with early top-source names/scores before final answer
- `event: heartbeat` with progress telemetry (`elapsed_ms`, token count while generating)
- `event: token` with incremental `delta`
- `event: error` when generation errors occur
- `event: done` with final `{ answer, sources, session_id, fallback }`

## Chat Sessions

### `GET /chat/sessions`
List chat sessions for the authenticated user.

Auth: `Authorization: Bearer <token>` required.

Query params:
- `kb_id` (optional): filter sessions by knowledge base

### `GET /chat/sessions/{session_id}`
Get session metadata and messages.

Auth: `Authorization: Bearer <token>` required.

Query params:
- `limit` (optional, default `100`, max `500`): number of latest messages returned

### `DELETE /chat/sessions/{session_id}`
Delete a chat session and its messages.

Auth: `Authorization: Bearer <token>` required.

## Chat Jobs

### `GET /chat/jobs/{job_id}`
Get status/result for a queued long-running chat job.

Auth: `Authorization: Bearer <token>` required.

Success response:

```json
{
  "job_id": "9bc6c3ea6dc149aeb8492444b91f7482",
  "status": "completed",
  "session_id": "optional-session-id",
  "answer": "...",
  "sources": [],
  "error_message": null,
  "created_at": "2026-02-22T10:10:10.000000",
  "started_at": "2026-02-22T10:10:11.000000",
  "finished_at": "2026-02-22T10:10:18.000000"
}
```

## Health

### `GET /`
Simple HTML root page with a docs link.
