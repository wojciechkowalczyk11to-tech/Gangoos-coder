"""
Gangus LLM client — connects to Qwen3:8b on the LLM host via Ollama.
Fallback chain: Ollama → Groq → DeepSeek.
All hosts read from env vars — no IPs hardcoded.
"""
import asyncio
import logging
import os
import time
from typing import Optional

import httpx

log = logging.getLogger("gangus.llm")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# Timeout matrix (seconds)
HEALTH_TIMEOUT = 5
CHAT_TIMEOUT = 120
FALLBACK_TIMEOUT = 60

# Retry policy
MAX_RETRIES = 2
RETRY_BACKOFF = [1.0, 3.0]  # seconds between retries


async def health_check(host: str = OLLAMA_HOST, timeout: int = HEALTH_TIMEOUT) -> bool:
    """Check if Ollama is reachable before sending a chat request."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{host}/api/tags")
            return resp.status_code == 200
    except Exception as e:
        log.warning(f"Ollama health check failed ({host}): {e}")
        return False


async def _chat_ollama(messages: list[dict], timeout: int = CHAT_TIMEOUT) -> str:
    """Single attempt to Ollama. Raises on failure."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{OLLAMA_HOST}/v1/chat/completions",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _chat_groq(messages: list[dict]) -> str:
    """Fallback: Groq qwen-qwq-32b."""
    async with httpx.AsyncClient(timeout=FALLBACK_TIMEOUT) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={"model": "qwen-qwq-32b", "messages": messages},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _chat_deepseek(messages: list[dict]) -> str:
    """Fallback: DeepSeek deepseek-chat."""
    async with httpx.AsyncClient(timeout=FALLBACK_TIMEOUT) as client:
        resp = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={"model": "deepseek-chat", "messages": messages},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def chat(prompt: str, system: str = "") -> str:
    """
    Send a prompt to the best available LLM.
    Priority: Ollama (Qwen3:8b) → Groq → DeepSeek.
    Retries Ollama up to MAX_RETRIES before falling back.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # 1. Try Ollama with health check + retry
    if await health_check():
        last_err: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                result = await _chat_ollama(messages)
                log.info(f"Ollama OK (attempt {attempt + 1})")
                return result
            except Exception as e:
                last_err = e
                log.warning(f"Ollama attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)])
        log.error(f"Ollama failed after {MAX_RETRIES + 1} attempts: {last_err}")
    else:
        log.warning(f"Ollama unreachable at {OLLAMA_HOST} — skipping to fallback")

    # 2. Fallback: Groq
    if GROQ_API_KEY:
        try:
            result = await _chat_groq(messages)
            log.info("Groq fallback OK")
            return result
        except Exception as e:
            log.warning(f"Groq fallback failed: {e}")

    # 3. Fallback: DeepSeek
    if DEEPSEEK_API_KEY:
        result = await _chat_deepseek(messages)
        log.info("DeepSeek fallback OK")
        return result

    raise RuntimeError(
        "All LLM providers unavailable. "
        "Set OLLAMA_HOST, GROQ_API_KEY, or DEEPSEEK_API_KEY."
    )


if __name__ == "__main__":
    import sys
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Write a Rust function to reverse a string."
    result = asyncio.run(chat(prompt))
    print(result)
