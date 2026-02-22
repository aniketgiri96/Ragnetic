# Ingestion and Chunking

## Overview

Ragnetic ingests documents asynchronously via Celery:
upload -> object store -> DB record -> parse -> chunk -> embed -> Qdrant index.

## Document Types and Parsers

- **PDF:** PyMuPDF (`fitz`) — text per page, metadata includes page count.
- **TXT / MD:** Decoded as UTF-8 with replacement for invalid bytes.
- **DOCX:** `python-docx` — paragraph text concatenated.

Parsers are selected by MIME type or file extension. They return plain text and optional metadata (e.g. `pages`).

## Chunking

- **Hierarchical:** Split first by paragraph (double newline), then by size.
- **Size and overlap defaults:** `chunk_max_chars=600`, `chunk_overlap_chars=80`, `chunk_min_chars=180`.
- **Oversize handling:** Long segments are split by sentence boundaries, with word-wrap fallback.
- **Metadata:** Each chunk includes source metadata plus chunk index/count and character offsets.

## Pipeline Steps

1. **Upload:** File stored in MinIO; `Document` row created with `object_key`, `content_hash`, `status=pending`.
2. **Celery task:** `ingest_document(document_id)` loads file, parses text, chunks it, embeds chunks, and upserts points into Qdrant.
3. **Embedding mode:** Uses local `sentence-transformers` when available, otherwise deterministic pseudo-vectors for fallback/testing.
4. **Status:** Document moves to `processing`, then `indexed` or `failed` with `error_message`.

## Idempotency and Dedup

- `content_hash` (SHA-256) is stored and checked at upload time.
- Re-uploading identical content into the same KB returns the existing `document_id` with `deduplicated=true` and skips re-enqueue.
