"""
E3: File-based session persistence (Teams/Tasks pattern).
Stores CodeAct sessions as JSONL + JSON files — no database, git-friendly.

Layout:
  .gangus/sessions/{session-id}/messages.jsonl
  .gangus/tasks/{task-name}/state.json
"""
import fcntl
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict

log = logging.getLogger("nexus-mcp.session-store")

GANGUS_DIR = Path(os.getenv("GANGUS_DIR", ".gangus"))
SESSIONS_DIR = GANGUS_DIR / "sessions"
TASKS_DIR = GANGUS_DIR / "tasks"


# ── Low-level file helpers ───────────────────────────────────────────────────

def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json_atomic(path: Path, data: dict) -> None:
    """Write JSON atomically via temp file + rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict) -> None:
    """Append one record to a JSONL file with file lock for concurrent access."""
    _ensure_dir(path.parent)
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning(f"Corrupt JSONL line in {path}: {line[:80]}")
    return records


# ── MCP tools ────────────────────────────────────────────────────────────────

def register(mcp: FastMCP):

    class SessionWriteInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        session_id: Optional[str] = Field(None, description="Session ID (auto-generated if omitted)")
        role: str = Field(..., description="Message role: user | assistant | tool")
        content: str = Field(..., description="Message content", min_length=1)
        metadata: dict = Field(default_factory=dict, description="Optional metadata")

    @mcp.tool(name="session_write", annotations={"title": "Write Session Message", "destructiveHint": False})
    async def session_write(params: SessionWriteInput, ctx: Context) -> str:
        """Append a message to a session JSONL file.
        Creates the session directory if needed. Returns the session_id.
        Auto-generates training data from session logs.
        """
        sid = params.session_id or str(uuid.uuid4())
        path = SESSIONS_DIR / sid / "messages.jsonl"
        record = {
            "ts": time.time(),
            "role": params.role,
            "content": params.content,
            **params.metadata,
        }
        try:
            _append_jsonl(path, record)
        except Exception as e:
            return f"ERROR writing session {sid}: {e}"
        return f"OK session_id={sid}"

    class SessionReadInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        session_id: str = Field(..., description="Session ID to read")
        last_n: Optional[int] = Field(None, description="Return only last N messages")

    @mcp.tool(name="session_read", annotations={"title": "Read Session Messages", "readOnlyHint": True})
    async def session_read(params: SessionReadInput, ctx: Context) -> str:
        """Read all messages for a session."""
        path = SESSIONS_DIR / params.session_id / "messages.jsonl"
        records = _read_jsonl(path)
        if params.last_n:
            records = records[-params.last_n:]
        if not records:
            return f"Session {params.session_id} not found or empty."
        lines = [f"[{r['role']}] {r['content'][:200]}" for r in records]
        return f"Session {params.session_id} ({len(records)} messages):\n" + "\n".join(lines)

    class TaskStateInput(BaseModel):
        model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
        task_name: str = Field(..., description="Task identifier (slug)", min_length=1)
        state: dict = Field(..., description="Task state dict to persist")

    @mcp.tool(name="task_save", annotations={"title": "Save Task State", "destructiveHint": False})
    async def task_save(params: TaskStateInput, ctx: Context) -> str:
        """Persist task state as JSON. Git-friendly, debuggable, no database needed."""
        path = TASKS_DIR / params.task_name / "state.json"
        _ensure_dir(path.parent)
        try:
            _write_json_atomic(path, {"task": params.task_name, "ts": time.time(), **params.state})
        except Exception as e:
            return f"ERROR saving task {params.task_name}: {e}"
        return f"OK saved task {params.task_name}"

    class TaskLoadInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        task_name: str = Field(..., description="Task identifier to load")

    @mcp.tool(name="task_load", annotations={"title": "Load Task State", "readOnlyHint": True})
    async def task_load(params: TaskLoadInput, ctx: Context) -> str:
        """Load persisted task state."""
        path = TASKS_DIR / params.task_name / "state.json"
        if not path.exists():
            return f"Task {params.task_name} not found."
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            return f"ERROR reading task {params.task_name}: {e}"
        return json.dumps(data, indent=2)
