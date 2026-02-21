# Ragnetic — Visual Architecture

## System overview

```mermaid
flowchart TB
  subgraph User[" "]
    U[User]
  end

  subgraph UI["Frontend"]
    FE[Next.js 14 · Tailwind · Shadcn UI<br/>Dashboard · Chat · :3000]
  end

  subgraph API["Backend API"]
    BE[FastAPI · :8000]
  end

  subgraph Ingestion["Ingestion pipeline"]
    direction LR
    UP[Upload] --> STORE[MinIO]
    UP --> REC[PostgreSQL]
    REC --> CQ[Celery queue]
    CQ --> PARSE[Parse]
    PARSE --> CHUNK[Chunk]
    CHUNK --> EMBED[Embed]
    EMBED --> QD[Qdrant]
  end

  subgraph Query["Query / Chat flow"]
    direction LR
    AUTH[Auth JWT] --> HYBRID[Hybrid search]
    HYBRID --> RERANK[Rerank]
    RERANK --> CTX[Context]
    CTX --> LLM[Ollama / LLM]
    LLM --> STREAM[Stream]
  end

  subgraph Data["Data & services"]
    PG[(PostgreSQL<br/>users, docs, KBs)]
    QD[(Qdrant<br/>vectors)]
    REDIS[(Redis<br/>broker · cache)]
    MINIO[(MinIO<br/>files)]
    OLLAMA[Ollama<br/>local LLM]
  end

  U --> FE
  FE --> BE
  BE --> Ingestion
  BE --> Query
  BE --> PG
  BE --> QD
  BE --> REDIS
  BE --> MINIO
  BE --> OLLAMA
  CQ -.-> REDIS
```

## Containers (docker-compose)

| Service        | Port(s)  | Role                          |
|----------------|----------|-------------------------------|
| **frontend**   | 3000     | Next.js app                   |
| **backend**    | 8000     | FastAPI API                   |
| **celery_worker** | —     | Async ingestion tasks         |
| **celery_flower** | 5555   | Task monitoring               |
| **db**         | 5432     | PostgreSQL                    |
| **qdrant**     | 6333–6334| Vector store                  |
| **redis**      | 6379     | Celery broker + cache         |
| **minio**      | 9000, 9001 | Object storage + console   |
| **ollama**     | 11434    | Local LLM                     |

## Ingestion flow (simplified)

```mermaid
sequenceDiagram
  participant U as User
  participant FE as Frontend
  participant API as FastAPI
  participant Store as MinIO
  participant DB as PostgreSQL
  participant Redis as Redis
  participant Worker as Celery Worker
  participant Qdrant as Qdrant

  U->>FE: Upload file
  FE->>API: POST /upload
  API->>Store: Store file
  API->>DB: Document record (pending)
  API->>Redis: Enqueue task
  API-->>FE: 202 Accepted

  Redis->>Worker: ingest_document
  Worker->>Store: Get file
  Worker->>Worker: Parse → Chunk → Embed
  Worker->>Qdrant: Upsert vectors
  Worker->>DB: status = indexed
```

## Query / Chat flow (simplified)

```mermaid
sequenceDiagram
  participant U as User
  participant FE as Frontend
  participant API as FastAPI
  participant Qdrant as Qdrant
  participant LLM as Ollama/LLM

  U->>FE: Ask question
  FE->>API: POST /chat (stream)
  API->>API: Auth → Embed query
  API->>Qdrant: Hybrid search (vector + BM25)
  API->>API: Rerank → Build context
  API->>LLM: Prompt + context
  LLM-->>API: Stream tokens
  API-->>FE: SSE stream
  FE-->>U: Answer + citations
```
