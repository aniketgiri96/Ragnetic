# API Endpoints Reference

Base URL (local): `http://localhost:8000`

Interactive OpenAPI docs: `/docs`

## Auth

### `POST /auth/register`
Create a new user account.

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

Query params:
- `kb_id` (optional): target knowledge base ID

Form-data:
- `file`: PDF, TXT, MD, or DOCX

Success response:

```json
{
  "filename": "employee-handbook.pdf",
  "status": "queued",
  "document_id": 12,
  "deduplicated": false
}
```

If identical content already exists in the same knowledge base, upload returns the existing `document_id` with `deduplicated: true`.

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

Auth: `Authorization: Bearer <token>` required.

Request body:

```json
{
  "message": "What is our PTO policy?",
  "kb_id": 1,
  "session_id": "optional-session-id"
}
```

Success response:

```json
{
  "answer": "...",
  "sources": [
    {
      "snippet": "...",
      "metadata": {
        "source": "employee-handbook.pdf",
        "doc_id": 12
      }
    }
  ]
}
```

## Health

### `GET /`
Simple HTML root page with a docs link.
