"""Tests for audit logging module."""

import json
import tempfile
from pathlib import Path

import pytest
from audit import AuditLogger, redact_value, hash_payload


class TestRedactionLogic:
    """Test sensitive data redaction."""

    def test_redact_token(self):
        """Tokens are redacted."""
        data = {"api_token": "secret123"}
        redacted = redact_value(data)
        assert redacted["api_token"] == "<redacted>"

    def test_redact_various_secrets(self):
        """Various secret names are redacted."""
        data = {
            "password": "pass123",
            "secret_key": "key456",
            "authorization": "Bearer token",
            "api_key": "key789",
        }
        redacted = redact_value(data)
        for key in data:
            assert redacted[key] == "<redacted>"

    def test_preserve_non_secrets(self):
        """Non-secret fields preserved."""
        data = {
            "query": "find users",
            "limit": 10,
            "api_key": "secret",
        }
        redacted = redact_value(data)
        assert redacted["query"] == "find users"
        assert redacted["limit"] == 10
        assert redacted["api_key"] == "<redacted>"

    def test_nested_redaction(self):
        """Nested secrets are redacted."""
        data = {
            "user": {
                "name": "alice",
                "password": "pass123",
            },
            "config": {
                "api_token": "token456",
            },
        }
        redacted = redact_value(data)
        assert redacted["user"]["name"] == "alice"
        assert redacted["user"]["password"] == "<redacted>"
        assert redacted["config"]["api_token"] == "<redacted>"

    def test_list_redaction(self):
        """Lists are redacted recursively."""
        data = [
            {"password": "pass1"},
            {"name": "safe"},
        ]
        redacted = redact_value(data)
        assert redacted[0]["password"] == "<redacted>"
        assert redacted[1]["name"] == "safe"

    def test_preserve_non_dict(self):
        """Non-dict/list values preserved."""
        assert redact_value("string") == "string"
        assert redact_value(123) == 123
        assert redact_value(None) is None


class TestPayloadHashing:
    """Test payload hashing for integrity."""

    def test_hash_deterministic(self):
        """Same payload produces same hash."""
        payload = {"query": "test", "limit": 10}
        hash1 = hash_payload(payload)
        hash2 = hash_payload(payload)
        assert hash1 == hash2

    def test_hash_order_independent(self):
        """Hash is order-independent (JSON sorts keys)."""
        payload1 = {"a": 1, "b": 2}
        payload2 = {"b": 2, "a": 1}
        assert hash_payload(payload1) == hash_payload(payload2)

    def test_hash_different_for_different_data(self):
        """Different payloads produce different hashes."""
        hash1 = hash_payload({"a": 1})
        hash2 = hash_payload({"a": 2})
        assert hash1 != hash2

    def test_hash_redaction_consistent(self):
        """Redaction is consistent in hashing."""
        payload_with_secret = {"data": "test", "password": "secret"}
        payload_without_secret = {"data": "test"}
        # Hashes differ because redacted version still includes key
        h1 = hash_payload(payload_with_secret)
        h2 = hash_payload(payload_without_secret)
        assert h1 != h2


class TestAuditLogger:
    """Test audit logging."""

    def test_log_event_basic(self):
        """Basic event logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path)

            event = logger.log_event(
                tool_name="test_tool",
                caller="test_caller",
                status="success",
                duration_ms=100,
            )

            assert event["tool_name"] == "test_tool"
            assert event["status"] == "success"
            assert event["duration_ms"] == 100
            assert "timestamp" in event
            assert "params_hash" in event

    def test_log_event_with_params(self):
        """Log event with redaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path)

            params = {"query": "test", "api_key": "secret123"}
            event = logger.log_event(
                tool_name="test",
                caller="caller",
                status="success",
                duration_ms=50,
                params=params,
            )

            assert event["params_preview"]["query"] == "test"
            assert event["params_preview"]["api_key"] == "<redacted>"

    def test_log_event_with_error(self):
        """Log event with error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path)

            event = logger.log_event(
                tool_name="test",
                caller="caller",
                status="error",
                duration_ms=10,
                error="Something failed",
            )

            assert event["status"] == "error"
            assert event["error"] == "Something failed"

    def test_log_file_creation(self):
        """Log file is created with proper format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "subdir" / "audit.jsonl"
            logger = AuditLogger(log_path)

            logger.log_event(
                tool_name="test1",
                caller="caller1",
                status="success",
                duration_ms=100,
            )

            logger.log_event(
                tool_name="test2",
                caller="caller2",
                status="failure",
                duration_ms=50,
            )

            assert log_path.exists()
            lines = log_path.read_text().strip().split("\n")
            assert len(lines) == 2

            # Parse as JSONL
            for line in lines:
                data = json.loads(line)
                assert "tool_name" in data
                assert "timestamp" in data

    def test_log_concurrent_writes(self):
        """Multiple log events are written correctly."""
        import threading

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path)

            def log_events(n):
                for i in range(n):
                    logger.log_event(
                        tool_name=f"tool_{i}",
                        caller="caller",
                        status="success",
                        duration_ms=i,
                    )

            threads = [
                threading.Thread(target=log_events, args=(5,))
                for _ in range(3)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All events should be logged
            lines = log_path.read_text().strip().split("\n")
            assert len(lines) == 15
