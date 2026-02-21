# Retrieval and Reranking

## Current Implementation

- **Hybrid retrieval:** Dense vector search (Qdrant cosine) plus sparse lexical scoring (BM25 over a bounded corpus snapshot).
- **Fusion:** Dense and sparse ranks are merged with Reciprocal Rank Fusion (RRF).
- **Optional reranking:** Top-N fused candidates are reranked with a local cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) when `sentence-transformers` is available.
- **Collection model:** One Qdrant collection per knowledge base and embedding model version (`ragnetic_kb{id}_v1`).
- **Search API:** `GET /search/?query=...&kb_id=...` returns snippet, fused score, dense score, sparse score, and metadata.

## Configurable Parameters

- `RETRIEVAL_TOP_K` (default `5`)
- `RETRIEVAL_DENSE_LIMIT` (default `30`)
- `RETRIEVAL_SPARSE_POOL` (default `800`)
- `RETRIEVAL_RERANK_TOP_N` (default `12`)

## Context Assembly

- **Dynamic chunk selection:** Add chunks until ~75% of model context limit.
- **Ordering:** Higher-scoring chunks placed at start and end to mitigate “lost in the middle” behavior.
