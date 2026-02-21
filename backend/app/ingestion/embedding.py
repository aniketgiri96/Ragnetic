"""Embedding service: sentence-transformers or stub."""
_model = None


def _get_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        return _model
    except Exception:
        return None


def get_embedding_dim() -> int:
    m = _get_model()
    if m is not None:
        return m.get_sentence_embedding_dimension()
    return 384


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return list of vectors for each text."""
    m = _get_model()
    if m is not None:
        return m.encode(texts, convert_to_numpy=True).tolist()
    # Stub: deterministic pseudo-vectors for testing
    import hashlib
    dim = 384
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode()).digest()
        vec = [(int(h[i % 32]) - 128) / 128.0 for i in range(dim)]
        out.append(vec)
    return out
