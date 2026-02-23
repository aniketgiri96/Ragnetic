"""LLM adapter: Ollama (local) and optional OpenAI fallback."""
from __future__ import annotations

import json
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _ollama_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            if isinstance(data.get("error"), str) and data["error"].strip():
                return data["error"].strip()
            if isinstance(data.get("message"), str) and data["message"].strip():
                return data["message"].strip()
        if isinstance(data, str) and data.strip():
            return data.strip()
        return str(data)[:240]
    except Exception:
        text = (response.text or "").strip()
        if text:
            return text[:240]
        return response.reason_phrase or "unknown error"


async def generate(prompt: str, system: str | None = None) -> str:
    """Generate completion. Returns full string."""
    if settings.openai_api_key:
        return await _generate_openai(prompt, system=system)
    return await _generate_ollama(prompt, system=system)


async def generate_stream(prompt: str, system: str | None = None):
    """Yield completion chunks as they arrive."""
    if settings.openai_api_key:
        try:
            async for chunk in _generate_openai_stream(prompt, system=system):
                yield chunk
            return
        except ImportError:
            # OpenAI SDK unavailable; fall back to local Ollama streaming.
            pass
    async for chunk in _generate_ollama_stream(prompt, system=system):
        yield chunk


async def _generate_ollama(prompt: str, system: str | None = None) -> str:
    full_prompt = prompt
    if system:
        full_prompt = f"{system}\n\n{prompt}"
    url = f"{settings.ollama_url.rstrip('/')}/api/generate"
    tags_url = f"{settings.ollama_url.rstrip('/')}/api/tags"
    num_predict = int(settings.ollama_num_predict)
    temperature = float(settings.ollama_temperature)
    payload = {
        "model": settings.ollama_model,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
        },
    }
    timeout = httpx.Timeout(
        timeout=float(settings.llm_timeout_seconds),
        connect=float(settings.llm_connect_timeout_seconds),
    )
    model_check_timeout = httpx.Timeout(
        timeout=float(settings.llm_model_check_timeout_seconds),
        connect=float(settings.llm_connect_timeout_seconds),
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Fast-fail if the configured model is not available locally.
        try:
            tags_resp = await client.get(tags_url, timeout=model_check_timeout)
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

        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.ReadTimeout as exc:
            retry_predict = max(64, num_predict // 2)
            if retry_predict >= num_predict:
                raise RuntimeError(
                    f"Ollama request timed out after {settings.llm_timeout_seconds}s. "
                    "Increase LLM_TIMEOUT_SECONDS or lower OLLAMA_NUM_PREDICT."
                ) from exc

            retry_payload = {
                **payload,
                "options": {
                    **payload["options"],
                    "num_predict": retry_predict,
                },
            }
            logger.warning(
                "Ollama timed out after %ss for model=%s; retrying once with num_predict=%s",
                settings.llm_timeout_seconds,
                settings.ollama_model,
                retry_predict,
            )
            try:
                resp = await client.post(url, json=retry_payload)
                resp.raise_for_status()
            except httpx.ReadTimeout as retry_exc:
                raise RuntimeError(
                    f"Ollama request timed out after retry. Current timeout: {settings.llm_timeout_seconds}s."
                ) from retry_exc
            except httpx.HTTPStatusError as retry_exc:
                detail = _ollama_error_detail(retry_exc.response)
                raise RuntimeError(
                    f"Ollama returned {retry_exc.response.status_code} on retry: {detail}"
                ) from retry_exc
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Could not connect to Ollama at {settings.ollama_url}") from exc
        except httpx.HTTPStatusError as exc:
            detail = _ollama_error_detail(exc.response)
            raise RuntimeError(f"Ollama returned {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Ollama request failed: {exc.__class__.__name__}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError("Ollama returned invalid JSON response.") from exc
        return data.get("response", "")


async def _generate_ollama_stream(prompt: str, system: str | None = None):
    full_prompt = prompt
    if system:
        full_prompt = f"{system}\n\n{prompt}"
    url = f"{settings.ollama_url.rstrip('/')}/api/generate"
    tags_url = f"{settings.ollama_url.rstrip('/')}/api/tags"
    payload = {
        "model": settings.ollama_model,
        "prompt": full_prompt,
        "stream": True,
        "options": {
            "num_predict": int(settings.ollama_num_predict),
            "temperature": float(settings.ollama_temperature),
        },
    }
    timeout = httpx.Timeout(
        timeout=float(settings.llm_timeout_seconds),
        connect=float(settings.llm_connect_timeout_seconds),
    )
    model_check_timeout = httpx.Timeout(
        timeout=float(settings.llm_model_check_timeout_seconds),
        connect=float(settings.llm_connect_timeout_seconds),
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            tags_resp = await client.get(tags_url, timeout=model_check_timeout)
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
            pass

        try:
            async with client.stream("POST", url, json=payload) as resp:
                if resp.status_code >= 400:
                    detail = _ollama_error_detail(resp)
                    raise RuntimeError(f"Ollama returned {resp.status_code}: {detail}")
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(item, dict):
                        continue
                    if isinstance(item.get("error"), str) and item["error"].strip():
                        raise RuntimeError(f"Ollama stream error: {item['error'].strip()}")
                    chunk = item.get("response") or ""
                    if chunk:
                        yield chunk
                    if item.get("done"):
                        break
        except httpx.ReadTimeout as exc:
            raise RuntimeError(
                f"Ollama streaming request timed out after {settings.llm_timeout_seconds}s."
            ) from exc
        except httpx.ConnectError as exc:
            raise RuntimeError(f"Could not connect to Ollama at {settings.ollama_url}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Ollama streaming request failed: {exc.__class__.__name__}") from exc


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


async def _generate_openai_stream(prompt: str, system: str | None = None):
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise ImportError("OpenAI SDK not installed") from exc

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    stream = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        stream=True,
    )
    async for event in stream:
        if not event.choices:
            continue
        delta = event.choices[0].delta.content
        if delta:
            yield delta
