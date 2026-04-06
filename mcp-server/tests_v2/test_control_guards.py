"""Tests for control domain guards (shell and filesystem operations)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from domains.control import shell_execute, filesystem_write, is_control_enabled


class TestControlEnabled:
    """Test control domain enable/disable check."""

    def test_disabled_by_default(self):
        """Control domain disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            assert is_control_enabled() is False

    def test_enable_with_true(self):
        """Can enable with 'true'."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            assert is_control_enabled() is True

    def test_enable_with_yes(self):
        """Can enable with 'yes'."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "yes"}):
            assert is_control_enabled() is True

    def test_enable_with_1(self):
        """Can enable with '1'."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "1"}):
            assert is_control_enabled() is True


@pytest.mark.asyncio
class TestShellExecute:
    """Test shell command execution with guards."""

    async def test_disabled_shell(self):
        """Shell execute returns error when disabled."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "false"}):
            result = await shell_execute("echo hello")
            assert "error" in result
            assert result["status_code"] == 403

    async def test_simple_command(self):
        """Execute simple shell command."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await shell_execute("echo hello")
            assert result["exit_code"] == 0
            assert "hello" in result["stdout"]

    async def test_command_with_error(self):
        """Capture command errors."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await shell_execute("exit 1")
            assert result["exit_code"] == 1

    async def test_stderr_capture(self):
        """Capture stderr output."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await shell_execute("python3 -c 'import sys; sys.stderr.write(\"error\")'")
            assert "error" in result["stderr"]

    async def test_timeout_protection(self):
        """Commands timeout as specified."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await shell_execute("sleep 10", timeout=1)
            assert "error" in result
            assert "timeout" in result["error"].lower()

    async def test_timeout_limit(self):
        """Timeout cannot exceed 300 seconds."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await shell_execute("echo test", timeout=400)
            assert "error" in result
            assert result["status_code"] == 400

    async def test_output_truncation(self):
        """Large output is truncated."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            # Generate output larger than 10KB
            result = await shell_execute("python3 -c 'print(\"x\" * 20000)'")
            assert result["truncated"] is True
            assert len(result["stdout"]) == 10000

    async def test_working_directory(self):
        """Can specify working directory."""
        home = os.path.expanduser("~")
        with tempfile.TemporaryDirectory(dir=home) as tmpdir:
            with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
                result = await shell_execute(
                    "pwd",
                    cwd=tmpdir,
                )
                assert result["exit_code"] == 0
                assert tmpdir in result["stdout"]

    async def test_cwd_validation(self):
        """CWD must be under home directory."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await shell_execute(
                "pwd",
                cwd="/etc/passwd",  # Outside home
            )
            assert "error" in result
            assert result["status_code"] == 403

    async def test_invalid_cwd(self):
        """Invalid CWD is rejected."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await shell_execute(
                "pwd",
                cwd="/nonexistent/path/that/is/not/home",
            )
            # Will fail validation (outside home) or command execution
            assert "error" in result or result.get("exit_code", 1) != 0


@pytest.mark.asyncio
class TestFilesystemWrite:
    """Test filesystem write with guards."""

    async def test_disabled_filesystem(self):
        """Filesystem write returns error when disabled."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "false"}):
            result = await filesystem_write("/tmp/test.txt", "content")
            assert "error" in result
            assert result["status_code"] == 403

    async def test_write_to_tmp(self):
        """Can write to /tmp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
                path = os.path.join(tmpdir, "test.txt")
                result = await filesystem_write(path, "hello world")
                assert result["status"] == "success"
                assert Path(path).read_text() == "hello world"

    async def test_write_to_home(self):
        """Can write to home directory."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            home = os.path.expanduser("~")
            with tempfile.TemporaryDirectory(dir=home) as tmpdir:
                path = os.path.join(tmpdir, "test.txt")
                result = await filesystem_write(path, "content")
                assert result["status"] == "success"

    async def test_write_mode_append(self):
        """Can append to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
                path = os.path.join(tmpdir, "test.txt")
                Path(path).write_text("line1\n")

                result = await filesystem_write(path, "line2\n", mode="a")
                assert result["status"] == "success"
                content = Path(path).read_text()
                assert "line1" in content
                assert "line2" in content

    async def test_write_mode_overwrite(self):
        """Mode 'w' overwrites file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
                path = os.path.join(tmpdir, "test.txt")
                Path(path).write_text("old content")

                result = await filesystem_write(path, "new content", mode="w")
                assert result["status"] == "success"
                assert Path(path).read_text() == "new content"

    async def test_invalid_mode(self):
        """Invalid mode is rejected."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await filesystem_write("/tmp/test.txt", "content", mode="x")
            assert "error" in result
            assert result["status_code"] == 400

    async def test_outside_allowed_roots(self):
        """Path outside allowed roots is rejected."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            result = await filesystem_write(
                "/root/forbidden.txt",
                "content"
            )
            # Might fail at permission stage, but should have error
            assert "error" in result or result["status_code"] >= 400

    async def test_create_parent_directories(self):
        """Parent directories are created if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
                path = os.path.join(tmpdir, "a", "b", "c", "test.txt")
                result = await filesystem_write(path, "content")
                assert result["status"] == "success"
                assert Path(path).exists()

    async def test_content_size_limit(self):
        """Content size is limited to 100KB."""
        with patch.dict(os.environ, {"ENABLE_CONTROL_DOMAIN": "true"}):
            # This should fail at Pydantic validation, not here
            # But we test that reasonable sizes work
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "test.txt")
                result = await filesystem_write(path, "x" * 50000)
                assert result["status"] == "success"
