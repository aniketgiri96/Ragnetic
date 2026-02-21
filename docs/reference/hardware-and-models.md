# Reference: Hardware and Models

## Recommended Hardware (Self-Hosting)

| Tier | Hardware | Capacity | Use case |
|------|----------|----------|----------|
| Starter | 4 CPU, 8 GB RAM, 50 GB SSD | Up to ~10K documents | Personal / small team |
| Team | 8 CPU, 16 GB RAM, 200 GB SSD | Up to ~100K documents | Team or department |
| Enterprise | 16 CPU, 64 GB RAM, 1 TB NVMe (+ optional GPU) | 1M+ documents | Company-wide |
| Cloud (e.g. AWS) | c5.2xlarge + r5.large DB | 100K+ (managed) | Cloud-hosted enterprise |

## Embedding Models (Launch)

| Model | Dims | Speed | Quality | Best for |
|-------|------|-------|---------|----------|
| all-MiniLM-L6-v2 | 384 | Very fast | Good | Default balance |
| BAAI/bge-large-en-v1.5 | 1024 | Medium | Excellent | High-quality production |
| nomic-embed-text | 768 | Fast | Very good | Local (e.g. Ollama) |
| text-embedding-3-small | 1536 | API | Excellent | OpenAI fallback |
| text-embedding-3-large | 3072 | API | Best | Max quality (higher cost) |

## LLMs (Launch)

| Model | Provider | Privacy | Quality | Notes |
|-------|----------|--------|---------|--------|
| Llama 3.1 8B | Ollama (local) | Full | Good | Default local; 8 GB VRAM or CPU |
| Llama 3.1 70B | Ollama (local) | Full | Excellent | 48 GB+ VRAM |
| Mistral 7B | Ollama (local) | Full | Good | Fast local option |
| GPT-4o | OpenAI | None | Best | Cloud, max quality |
| Claude 3.5 Sonnet | Anthropic | None | Best | Strong reasoning |
| Gemini 1.5 Pro | Google | None | Excellent | Long context (1M tokens) |
