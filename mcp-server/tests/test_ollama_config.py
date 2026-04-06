"""Tests for Ollama and Groq config fields."""
import os
import pytest
from config import Settings


def test_ollama_defaults_to_localhost():
    s = Settings()
    assert "localhost" in s.OLLAMA_HOST or "127.0.0.1" in s.OLLAMA_HOST


def test_ollama_host_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://my-llm-host:11434")
    s = Settings()
    assert s.OLLAMA_HOST == "http://my-llm-host:11434"


def test_ollama_model_default():
    s = Settings()
    assert s.OLLAMA_DEFAULT_MODEL == "qwen3:8b"


def test_groq_key_empty_by_default():
    s = Settings()
    assert s.GROQ_API_KEY == "" or s.GROQ_API_KEY == os.getenv("GROQ_API_KEY", "")


def test_no_hardcoded_ips_in_defaults():
    """Ensure no production IPs are hardcoded as defaults."""
    s = Settings()
    private_ips = ["164.90.", "46.101.", "10.19."]
    for ip in private_ips:
        assert ip not in s.OLLAMA_HOST, f"Hardcoded IP {ip} found in OLLAMA_HOST default"
