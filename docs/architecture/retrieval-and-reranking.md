# Retrieval and Reranking

## Current Implementation

- **Hybrid retrieval:** Dense vector search (Qdrant cosine) plus sparse lexical scoring (in-process BM25 over a bounded corpus snapshot).
- **Fusion:** Dense and sparse ranks are merged with Reciprocal Rank Fusion (RRF).
- **Optional reranking:** Top-N fused candidates can be reranked with a local cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) when enabled and available.
- **Collection model:** One Qdrant collection per knowledge base and embedding version (`ragnetic_kb{id}_v1`).
- **Search API:** `GET /search/?query=...&kb_id=...` returns snippet, fused score, dense score, sparse score, and metadata.

## Configurable Parameters

- `RETRIEVAL_TOP_K` (default `5`)
- `RETRIEVAL_DENSE_LIMIT` (default `20`)
- `RETRIEVAL_SPARSE_POOL` (default `240`)
- `RETRIEVAL_RERANK_TOP_N` (default `8`)
- `RETRIEVAL_ENABLE_CROSS_ENCODER` (default `false`)

## Context Assembly

- **Source count limit:** `CHAT_CONTEXT_MAX_SOURCES` controls max retrieved snippets used for prompt context (default `4`).
- **Per-source size limit:** `CHAT_CONTEXT_MAX_CHARS_PER_SOURCE` truncates each source block (default `420` chars).
- **History inclusion:** Last up to 10 messages from the same session are included for continuity.
