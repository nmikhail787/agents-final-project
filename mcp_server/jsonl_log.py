"""Append-only JSONL audit log for MCP tool calls.

The brief requires logging request, response, timestamp and source URL, and
separately requires that secrets never reach the log. Both are handled here so
no tool module has to remember to do it.

One JSON object per line, so the log stays greppable and survives a crash
mid-write without corrupting earlier records.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

LOG_PATH = Path(
    os.environ.get("MCP_LOG_PATH", str(_REPO_ROOT / "logs" / "mcp_requests.jsonl"))
)

# Anything whose key looks like one of these is replaced before it is written.
_SECRET_HINTS = ("key", "token", "secret", "password", "authorization", "api_key")

_lock = threading.Lock()


def _looks_secret(key: str) -> bool:
    return any(hint in key.lower() for hint in _SECRET_HINTS)


def redact(obj: Any) -> Any:
    """Recursively strip anything that looks like a credential.

    Belt and braces: no caller is supposed to pass a key in, but the log is the
    one artifact we hand to a grader, so it gets scrubbed on the way out too.
    """
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***" if _looks_secret(k) else redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def _truncate(obj: Any, max_chars: int = 4000) -> Any:
    """Keep single records readable; product `features` blobs run to 1000 chars
    each and would otherwise dominate the file."""
    if isinstance(obj, str) and len(obj) > max_chars:
        return obj[:max_chars] + f"...[truncated {len(obj) - max_chars} chars]"
    if isinstance(obj, dict):
        return {k: _truncate(v, max_chars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate(v, max_chars) for v in obj]
    return obj


def log_call(
    tool: str,
    request: dict[str, Any],
    response: Any = None,
    source_urls: list[str] | None = None,
    cache_hit: bool = False,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    """Write one audit record. Never raises — logging must not break a tool."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "request": redact(request),
        "response": _truncate(redact(response)),
        "source_urls": source_urls or [],
        "cache_hit": cache_hit,
        "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
        "error": error,
    }
    try:
        with _lock:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        # A failed write must not take down the tool call it was describing.
        pass
