# Ingestion and Chunking

## Overview

Ragnetic ingests documents asynchronously via Celery:
upload -> object store -> DB record -> parse -> chunk -> embed -> Qdrant index.

Ingestion attempts are tracked in dedicated ingestion-job records with progress and dead-letter entries for failed jobs.

## Document Types and Parsers

- **PDF:** PyMuPDF (`fitz`) — text per page, metadata includes page count.
- **TXT / MD:** Decoded as UTF-8 with replacement for invalid bytes.
- **DOCX:** `python-docx` — paragraph text concatenated.

Parsers are selected by MIME type or file extension. They return plain text and optional metadata (e.g. `pages`).

## Chunking

- **Hierarchical:** Detect section headings (Markdown and numbered headings), segment by paragraph, then split oversized segments by sentence boundaries.
- **Size and overlap defaults:** `chunk_max_chars=600`, `chunk_overlap_chars=80`, `chunk_overlap_sentences=1`, `chunk_min_chars=180`.
- **Oversize handling:** Long segments are split by sentence boundaries, with word-wrap fallback.
- **Metadata:** Each chunk includes source metadata plus chunk index/count, character offsets, and section breadcrumb metadata (`section_path`, `section_paths`, `section_title`) when headings are present.

## Pipeline Steps

1. **Upload:** File stored in MinIO; `Document` row created with `object_key`, `content_hash`, `status=pending`.
2. **Queue + job tracking:** An `ingestion_job` row is created (`queued`) and Celery task is enqueued with `document_id` + `ingestion_job_id`.
3. **Celery task:** `ingest_document(document_id, ingestion_job_id)` loads file, parses text, chunks it, embeds chunks, and upserts points into Qdrant.
3. **Embedding mode:** Uses local `sentence-transformers` when available, otherwise deterministic pseudo-vectors for fallback/testing.
4. **Status:** Document moves to `processing`, then `indexed` or `failed` with `error_message`; ingestion job mirrors lifecycle with progress updates.
5. **DLQ behavior:** Failed ingestion attempts create unresolved dead-letter entries; successful ingestion resolves dead letters for that document.

## Idempotency and Dedup

- `content_hash` (SHA-256) is stored and checked at upload time.
- Re-uploading identical content into the same KB returns the existing `document_id` with `deduplicated=true` and skips re-enqueue.
- Re-uploading the same filename with changed content (`replace_existing=true`) replaces object storage content and queues re-indexing for the existing document (incremental update path).
