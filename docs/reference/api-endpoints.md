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

## Organizations and Teams

### `GET /orgs/`
List organizations the current user belongs to.

Auth: `Authorization: Bearer <token>` required.

### `POST /orgs/`
Create an organization and assign caller as `owner`.

Auth: `Authorization: Bearer <token>` required.

Request body:

```json
{
  "name": "Acme Org",
  "description": "Primary workspace"
}
```

### `POST /orgs/{org_id}/members`
Add or update an organization member by email.

Auth: `Authorization: Bearer <token>` required.  
Permission: `admin` or `owner` in the organization.

Request body:

```json
{
  "email": "teammate@example.com",
  "role": "member"
}
```

Roles: `owner`, `admin`, `member`.

### `GET /orgs/{org_id}/teams`
List teams in an organization.

Auth: `Authorization: Bearer <token>` required.  
Permission: organization member.

### `POST /orgs/{org_id}/teams`
Create a team in an organization.

Auth: `Authorization: Bearer <token>` required.  
Permission: `admin` or `owner` in the organization.

### `POST /teams/{team_id}/members`
Add or update a team member by email.

Auth: `Authorization: Bearer <token>` required.  
Permission: `admin` or `owner` in the parent organization.

Request body:

```json
{
  "email": "member@example.com",
  "role": "member"
}
```

Roles: `manager`, `member`.

### `POST /teams/{team_id}/knowledge-bases/{kb_id}`
Assign team access to a knowledge base with a KB role.

Auth: `Authorization: Bearer <token>` required.  
Permission:
- `admin` or `owner` in the team's organization
- `owner` on the target knowledge base

Request body:

```json
{
  "role": "viewer"
}
```

KB roles: `owner`, `editor`, `viewer`, `api_user`.

### `GET /kb/{kb_id}/teams`
List team access mappings for a knowledge base.

Auth: `Authorization: Bearer <token>` required.  
Permission: `viewer` or higher on the KB.

## Onboarding

### `GET /onboarding/status`
Get first-time setup progress for the authenticated user.

Auth: `Authorization: Bearer <token>` required.

Response includes:
- `progress_percent`
- `completed_steps` / `total_steps`
- `steps[]` with completion state and recommended action path
- primary KB and document/query counts

### `POST /onboarding/sample-kb`
Create a starter knowledge base and queue ingestion of a sample onboarding document.

Auth: `Authorization: Bearer <token>` required.

Success response:

```json
{
  "kb_id": 12,
  "kb_name": "KnowAI Starter KB",
  "document_id": 44,
  "ingestion_job_id": 99,
  "status": "queued"
}
```

### `POST /kb/`
Create a new knowledge base and assign the caller as `owner`.

Auth: `Authorization: Bearer <token>` required.

Request body:

```json
{
  "name": "Ops KB",
  "description": "Runbooks and procedures"
}
```

### `PATCH /kb/{kb_id}`
Update KB name and/or description.

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

Request body (provide either or both fields):

```json
{
  "name": "Ops KB v2",
  "description": "Updated scope"
}
```

### `DELETE /kb/{kb_id}`
Delete a knowledge base and its indexed content.

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

### `GET /kb/{kb_id}/embeddings`
Get embedding namespace registry for a KB (active version, migration state, version history).

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

### `POST /kb/{kb_id}/embeddings/migrate`
Start zero-downtime embedding namespace migration to a target version.

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

Request body:

```json
{
  "target_version": "v2"
}
```

### `GET /kb/{kb_id}/audit`
List audit events for a KB (uploads, membership changes, KB updates, chat actions, etc.).

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

Query params:
- `limit` (optional, default `100`, max `500`)
- `action` (optional): exact action string filter

### `GET /kb/{kb_id}/analytics`
Get RAG observability metrics and drift alerts for a knowledge base.

Auth: `Authorization: Bearer <token>` required.  
Permission: `owner` on the KB.

Query params:
- `days` (optional, default `7`, min `1`, max `90`)

Response includes:
- Query volume metrics (total queries, mode breakdown, zero-result rate)
- Retrieval latency (`avg_retrieval_ms`, `p95_retrieval_ms`)
- Quality metrics (confidence/faithfulness rates and context proxies)
- Feedback metrics (thumbs-up/down, helpful rate)
- Top queries, zero-result queries, daily rollups, and drift alerts

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

Roles: `owner`, `editor`, `viewer`, `api_user`.

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
- `replace_existing` (optional, default `true`): replace and re-index when filename already exists with different content

Form-data:
- `file`: PDF, TXT, MD, or DOCX

Success response:

```json
{
  "filename": "employee-handbook.pdf",
  "status": "queued",
  "document_id": 12,
  "ingestion_job_id": 91
}
```

If identical content already exists in the same knowledge base, upload returns the existing `document_id` and includes `deduplicated: true`:

```json
{
  "filename": "employee-handbook.pdf",
  "status": "queued",
  "document_id": 12,
  "ingestion_job_id": 91,
  "deduplicated": true,
  "message": "Identical content already queued/indexed in this knowledge base."
}
```

If same filename already exists in the KB (case-insensitive) and content differs, upload can replace existing content:

```json
{
  "filename": "employee-handbook.pdf",
  "status": "queued",
  "document_id": 12,
  "ingestion_job_id": 92,
  "replaced": true,
  "message": "Existing document replaced and re-indexing queued."
}
```

If same filename exists and replacement is disabled (`replace_existing=false`), upload is blocked:

```json
{
  "filename": "employee-handbook.pdf",
  "status": "exists",
  "document_id": 12,
  "replace_required": true,
  "message": "Filename already exists in this knowledge base (case-insensitive). Set replace_existing=true to replace and re-index, or rename/delete the existing document first."
}
```

### `GET /documents`
List uploaded documents for a knowledge base.

Auth: `Authorization: Bearer <token>` required.
Permission: `viewer` or higher on KB.

Query params:
- `kb_id` (optional, defaults to first accessible KB)

Success response:

```json
[
  {
    "document_id": 12,
    "kb_id": 1,
    "filename": "employee-handbook.pdf",
    "status": "indexed",
    "error_message": null,
    "created_at": "2026-02-22T12:00:00.000000"
  }
]
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

### `PATCH /documents/{document_id}`
Rename a document.

Auth: `Authorization: Bearer <token>` required.
Permission: `editor` or higher on the KB.

Request body:

```json
{
  "filename": "handbook-v2.pdf"
}
```

Behavior:
- Updates filename
- Re-indexes document so source metadata matches new name

### `DELETE /documents/{document_id}`
Delete a document.

Auth: `Authorization: Bearer <token>` required.
Permission: `editor` or higher on the KB.

Behavior:
- Deletes vector chunks for that `doc_id`
- Deletes stored file object
- Removes document record from PostgreSQL

### `POST /documents/{document_id}/retry`
Retry ingestion for a document (useful for `failed` documents).

Auth: `Authorization: Bearer <token>` required.  
Permission: `editor` or higher on the KB.

Success response includes `ingestion_job_id` for the queued retry.

### `GET /kb/{kb_id}/ingestion/dead-letter`
List ingestion dead-letter entries for a KB.

Auth: `Authorization: Bearer <token>` required.  
Permission: `editor` or higher on the KB.

Query params:
- `limit` (optional, default `100`, max `500`)
- `resolved` (optional, default `false`)

### `POST /ingestion/dead-letter/{dead_letter_id}/retry`
Queue a retry for a dead-letter ingestion entry.

Auth: `Authorization: Bearer <token>` required.

### `GET /kb/{kb_id}/connectors/sync-state`
Get incremental sync cursor state for a connector scope.

Auth: `Authorization: Bearer <token>` required.  
Permission: `editor` or higher on the KB.

Query params:
- `source_type` (required)
- `scope_key` (required)

### `POST /kb/{kb_id}/connectors/sync-state`
Upsert incremental sync cursor state for a connector scope.

Auth: `Authorization: Bearer <token>` required.  
Permission: `editor` or higher on the KB.

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
  "assistant_message_id": 441,
  "confidence_score": 0.71,
  "low_confidence": false,
  "faithfulness_score": 0.82,
  "low_faithfulness": false,
  "citation_enforced": true,
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
- `event: done` with final `{ answer, sources, session_id, assistant_message_id, fallback, confidence_score, low_confidence, faithfulness_score, low_faithfulness, citation_enforced }`

### `POST /chat/feedback`
Submit thumbs-up/down feedback for an assistant response message.

Auth: `Authorization: Bearer <token>` required.

Request body:

```json
{
  "message_id": 441,
  "rating": "up",
  "comment": "Accurate and complete."
}
```

`rating` must be `up` or `down`.

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

Each message includes:
- `id`
- `role`
- `content`
- `created_at`
- `feedback_rating` (`up` / `down` / `null`)

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
  "assistant_message_id": 441,
  "feedback_rating": "up",
  "confidence_score": 0.67,
  "low_confidence": false,
  "faithfulness_score": 0.79,
  "low_faithfulness": false,
  "citation_enforced": true,
  "error_message": null,
  "created_at": "2026-02-22T10:10:10.000000",
  "started_at": "2026-02-22T10:10:11.000000",
  "finished_at": "2026-02-22T10:10:18.000000"
}
```

## Health

### `GET /`
Simple HTML root page with a docs link.
