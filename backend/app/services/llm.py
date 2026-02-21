"""LLM adapter: Ollama (local) and optional OpenAI fallback."""
import httpx

from app.core.config import settings


async def generate(prompt: str, system: str | None = None) -> str:
    """Generate completion. Returns full string."""
    if settings.openai_api_key:
        return await _generate_openai(prompt, system=system)
    return await _generate_ollama(prompt, system=system)


async def _generate_ollama(prompt: str, system: str | None = None) -> str:
    full_prompt = prompt
    if system:
        full_prompt = f"{system}\n\n{prompt}"
    url = f"{settings.ollama_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": full_prompt,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")


async def _generate_openai(prompt: str, system: str | None = None) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return await _generate_ollama(prompt, system=system)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
    )
    return resp.choices[0].message.content or ""
