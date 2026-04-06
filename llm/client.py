"""
Gangus LLM client — connects to Qwen3:8b on gangus-llm VM.
Fallback: Groq → DeepSeek when Ollama offline.
"""
import os
import httpx
import asyncio
from typing import AsyncIterator


OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://164.90.217.149:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")


async def chat(prompt: str, system: str = "", stream: bool = False) -> str:
    """Send prompt to Qwen3:8b. Falls back to Groq if unavailable."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    # Try Ollama first
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OLLAMA_HOST}/v1/chat/completions",
                json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[Ollama unavailable: {e}] → falling back to Groq")

    # Fallback: Groq (qwen-qwq-32b)
    if GROQ_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={"model": "qwen-qwq-32b", "messages": messages},
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[Groq failed: {e}] → trying DeepSeek")

    # Fallback: DeepSeek
    if DEEPSEEK_API_KEY:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                json={"model": "deepseek-chat", "messages": messages},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    raise RuntimeError("All LLM providers unavailable")


if __name__ == "__main__":
    result = asyncio.run(chat("Write a Rust function to reverse a string."))
    print(result)
