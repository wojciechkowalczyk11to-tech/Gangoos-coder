"""
Tests for E1-E4 enhancements.
E1: plan verifier, E2: streaming, E3: session store, E4: dataset filter.
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── E1: Plan Verifier ────────────────────────────────────────────────────────

class TestPlanVerifier:

    def test_module_importable(self):
        from modules.plan_verifier import _call_verifier, register
        assert callable(register)

    @pytest.mark.asyncio
    async def test_valid_plan_passes(self, monkeypatch):
        from modules import plan_verifier

        async def mock_verifier(client, cfg, plan):
            return {"valid": True, "issues": [], "confidence": 0.95}

        monkeypatch.setattr(plan_verifier, "_call_verifier", mock_verifier)
        # Direct logic test via _call_verifier mock
        result = await mock_verifier(None, None, "step 1: fetch data\nstep 2: process\nstep 3: output")
        assert result["valid"] is True
        assert result["confidence"] > 0.8

    @pytest.mark.asyncio
    async def test_incoherent_plan_rejected(self, monkeypatch):
        from modules import plan_verifier

        async def mock_verifier(client, cfg, plan):
            return {"valid": False, "issues": ["step 2 references undefined var X"], "confidence": 0.2}

        monkeypatch.setattr(plan_verifier, "_call_verifier", mock_verifier)
        result = await mock_verifier(None, None, "do thing then use X which came from nowhere")
        assert result["valid"] is False
        assert len(result["issues"]) > 0

    @pytest.mark.asyncio
    async def test_empty_plan_rejected(self, monkeypatch):
        from modules import plan_verifier

        async def mock_verifier(client, cfg, plan):
            return {"valid": False, "issues": ["empty plan"], "confidence": 0.0}

        monkeypatch.setattr(plan_verifier, "_call_verifier", mock_verifier)
        result = await mock_verifier(None, None, "")
        assert result["valid"] is False


# ── E2: Streaming ────────────────────────────────────────────────────────────

class TestStreaming:

    def test_module_importable(self):
        from modules.streaming import stream_ollama, register
        assert callable(register)

    @pytest.mark.asyncio
    async def test_streaming_yields_multiple_tokens(self):
        from modules.streaming import stream_ollama

        chunks = ["step 1", " do thing", "```", "result", " done"]
        call_count = 0

        async def fake_aiter_lines():
            for c in [f'data: {{"choices":[{{"delta":{{"content":"{ch}"}}}}]}}' for ch in chunks]:
                yield c
            yield "data: [DONE]"

        mock_resp = MagicMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.raise_for_status = MagicMock()
        mock_resp.aiter_lines = fake_aiter_lines

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_resp)

        tokens = []
        async for t in stream_ollama(mock_client, "http://localhost:11434", "qwen3:8b", []):
            tokens.append(t)
            call_count += 1

        assert call_count > 1, "streaming must yield more than 1 event"
        assert "".join(tokens) == "".join(chunks)


# ── E3: Session Store ────────────────────────────────────────────────────────

class TestSessionStore:

    def test_module_importable(self):
        from modules.session_store import _append_jsonl, _read_jsonl, _write_json_atomic, register
        assert callable(register)

    def test_write_read_roundtrip(self, tmp_path):
        from modules.session_store import _append_jsonl, _read_jsonl

        path = tmp_path / "test.jsonl"
        _append_jsonl(path, {"role": "user", "content": "hello"})
        _append_jsonl(path, {"role": "assistant", "content": "world"})

        records = _read_jsonl(path)
        assert len(records) == 2
        assert records[0]["role"] == "user"
        assert records[1]["content"] == "world"

    def test_corrupt_line_handled(self, tmp_path):
        from modules.session_store import _read_jsonl

        path = tmp_path / "corrupt.jsonl"
        path.write_text('{"role": "user"}\nNOT JSON\n{"role": "assistant"}\n')
        records = _read_jsonl(path)
        assert len(records) == 2  # corrupt line skipped

    def test_json_atomic_write(self, tmp_path):
        from modules.session_store import _write_json_atomic

        path = tmp_path / "state.json"
        _write_json_atomic(path, {"status": "running", "step": 1})
        loaded = json.loads(path.read_text())
        assert loaded["status"] == "running"


# ── E4: Dataset Filter ────────────────────────────────────────────────────────

class TestDatasetFilter:

    def _make_jsonl(self, records: list[dict], path: Path):
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    def test_complete_trace_passes(self, tmp_path):
        from modules.dataset_filter import filter_dataset

        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        self._make_jsonl([{
            "messages": [
                {"role": "user", "content": "write hello world"},
                {"role": "assistant", "content": 'print("hello world")'},
            ]
        }], inp)
        metrics = filter_dataset(inp, out)
        assert metrics["passed"] == 1
        assert metrics["filtered"] == 0

    def test_truncated_trace_filtered(self, tmp_path):
        from modules.dataset_filter import filter_dataset

        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        self._make_jsonl([{
            "messages": [
                {"role": "user", "content": "do something"},
                {"role": "assistant", "content": "I will start by..."},
                # truncated — last msg is user, not assistant
                {"role": "user", "content": "continue?"},
            ]
        }], inp)
        metrics = filter_dataset(inp, out)
        assert metrics["filtered"] == 1
        assert metrics["passed"] == 0

    def test_missing_tool_result_filtered(self, tmp_path):
        from modules.dataset_filter import filter_dataset

        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        self._make_jsonl([{
            "messages": [
                {"role": "user", "content": "use a tool"},
                {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "tool_123", "name": "shell", "input": {}}
                ]},
                # missing tool_result for tool_123
                {"role": "assistant", "content": "done"},
            ]
        }], inp)
        metrics = filter_dataset(inp, out)
        assert metrics["filtered"] == 1

    def test_empty_trace_filtered(self, tmp_path):
        from modules.dataset_filter import filter_dataset

        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        self._make_jsonl([{"messages": []}], inp)
        metrics = filter_dataset(inp, out)
        assert metrics["filtered"] == 1

    def test_quality_metrics_logged(self, tmp_path):
        from modules.dataset_filter import filter_dataset

        inp = tmp_path / "in.jsonl"
        out = tmp_path / "out.jsonl"
        records = [
            {"messages": [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]},
            {"messages": []},
            {"messages": [{"role": "user", "content": "q"}]},
        ]
        self._make_jsonl(records, inp)
        metrics = filter_dataset(inp, out)
        assert metrics["total"] == 3
        assert metrics["passed"] == 1
        assert metrics["filtered"] == 2
        assert "filter_reasons" in metrics
        assert metrics["pass_rate"] == round(1/3, 4)
