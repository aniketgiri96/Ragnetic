# Contributing to Ragnetic

Thanks for contributing.

This repository is a monorepo:

- `backend/` FastAPI + Celery
- `frontend/` Next.js app
- `docs/` product, architecture, and usage docs

## Prerequisites

- Docker + Docker Compose plugin (`docker compose`)
- Python 3.11+
- Node.js 20+

## Local Development

### 1. Start dependencies

From the repository root:

```bash
docker compose up -d db redis qdrant minio
```

Optional local LLM service:

```bash
docker compose up -d ollama
```

### 2. Run backend locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If you need ingestion workers while developing upload/indexing:

```bash
cd backend
source .venv/bin/activate
celery -A app.core.celery_app worker --loglevel=info
```

### 3. Run frontend locally

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

App URLs:

- Frontend: `http://localhost:3000`
- Backend OpenAPI docs: `http://localhost:8000/docs`

## Validation Before PR

Run the checks that exist in this repository:

```bash
cd backend
source .venv/bin/activate
pytest
```

```bash
cd frontend
npm run build
```

If your change affects docs, update the relevant files in `README.md` or `docs/`.

## Pull Request Process

1. Create a branch from `main`.
2. Keep changes focused and include context in the PR description.
3. Update docs and examples when behavior changes.
4. Ensure local validation passes before opening a PR.

## Community Standards

- Code of Conduct: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)
- Security reporting: [`SECURITY.md`](SECURITY.md)
- Support channels: [`SUPPORT.md`](SUPPORT.md)
