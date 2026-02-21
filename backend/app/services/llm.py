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
    tags_url = f"{settings.ollama_url.rstrip('/')}/api/tags"
    payload = {
        "model": settings.ollama_model,
        "prompt": full_prompt,
        "stream": False,
    }
    timeout = httpx.Timeout(
        timeout=float(settings.llm_timeout_seconds),
        connect=float(settings.llm_connect_timeout_seconds),
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Fast-fail if the configured model is not available locally.
        try:
            tags_resp = await client.get(tags_url)
            if tags_resp.status_code == 200:
                data = tags_resp.json()
                models = data.get("models") or []
                names = {
                    (m.get("name") or "").split(":")[0]
                    for m in models
                    if isinstance(m, dict)
                }
                names_full = {m.get("name") for m in models if isinstance(m, dict)}
                configured = settings.ollama_model
                configured_base = configured.split(":")[0]
                if configured not in names_full and configured_base not in names:
                    raise RuntimeError(
                        f"Ollama model '{configured}' not found. Pull it with: ollama run {configured}"
                    )
        except httpx.HTTPError:
            # Continue to generation attempt; request may still succeed.
            pass

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
