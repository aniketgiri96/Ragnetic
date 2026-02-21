# Auth and First Query

This guide walks through the shortest working flow: register, login, upload, search, and chat.

## 1. Register

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"strong-password"}'
```

## 2. Login and capture token

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"strong-password"}' | jq -r '.access_token')

echo "$TOKEN"
```

If you do not have `jq`, copy the `access_token` manually from the JSON response.

## 3. Get knowledge base ID

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/kb/
```

Use the `id` from the response (usually `1` for default).

## 4. Upload a file

```bash
curl -X POST "http://localhost:8000/upload/?kb_id=1" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/absolute/path/to/your-file.pdf"
```

Copy `document_id` from the response.

## 5. Wait for ingestion

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/documents/<document_id>/status
```

Proceed when `status` is `indexed`.

## 6. Search

```bash
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/search/?query=vacation+policy&kb_id=1"
```

## 7. Chat with RAG

```bash
curl -X POST http://localhost:8000/chat/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize the vacation policy","kb_id":1,"session_id":"demo-session-1"}'
```

Using `session_id` keeps multi-turn context for the same conversation.  
If omitted, backend generates and returns a new `session_id`.

## UI path

You can do the same flow from the frontend:

1. `http://localhost:3000/login`
2. `http://localhost:3000/upload`
3. `http://localhost:3000/search`
4. `http://localhost:3000/chat`
