# Reference: Hardware and Models

## Recommended Hardware (Self-Hosting)

| Tier | Hardware | Capacity | Use case |
|------|----------|----------|----------|
| Starter | 4 CPU, 8 GB RAM, 50 GB SSD | Up to ~10K documents | Personal / small team |
| Team | 8 CPU, 16 GB RAM, 200 GB SSD | Up to ~100K documents | Team or department |
| Enterprise | 16 CPU, 64 GB RAM, 1 TB NVMe (+ optional GPU) | 1M+ documents | Company-wide |
| Cloud (e.g. AWS) | c5.2xlarge + r5.large DB | 100K+ (managed) | Cloud-hosted enterprise |

## Embedding Runtime

- Default embedding model: `all-MiniLM-L6-v2` (via `sentence-transformers`)
- Vector dimension: `384`
- Fallback mode: deterministic pseudo-vectors when `sentence-transformers` is not installed

## LLM Provider Support (Current)

| Provider | Status | Notes |
|----------|--------|-------|
| Ollama | Supported (default) | Local model endpoint via `OLLAMA_URL`, model via `OLLAMA_MODEL` |
| OpenAI | Supported (optional fallback) | Used when `OPENAI_API_KEY` is set and OpenAI SDK is installed |

## Common Local Ollama Models

| Model | Typical profile | Notes |
|-------|-----------------|-------|
| `llama3.2` | Balanced default | Good quality/latency for local use |
| `mistral` | Faster responses | Lightweight option for CPU-bound hosts |
| `llama3.1:70b` | High quality, high resource usage | Requires large GPU memory |
