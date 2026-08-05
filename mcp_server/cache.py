"""TTL cache for MCP tool responses.

One implementation, instantiated once per tool. The two tools have genuinely
different staleness semantics and must not share a single cache:

    web.search  live prices and stock; must expire inside the 60-300s window
                the project brief requires.
    rag.search  a static Chroma index that only changes when someone reruns
                build_index.py, so a short TTL would just throw away work.

Deliberately dependency-free: `cachetools` is not in requirements.txt (it is
only present in the local anaconda env as somebody else's transitive dep), so
depending on it would work here and break in a clean venv.
"""

import json
import threading
import time
from typing import Any, Callable


def make_key(*parts: Any) -> str:
    """Stable cache key from arbitrary JSON-able parts.

    sort_keys matters: {"a":1,"b":2} and {"b":2,"a":1} are the same query and
    must hit the same cache entry.
    """
    return json.dumps(parts, sort_keys=True, default=str)


class TTLCache:
    """Thread-safe mapping with per-entry expiry and LRU-ish size bounding."""

    def __init__(self, ttl_seconds: float, max_entries: int = 512):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> tuple[bool, Any]:
        """Return (hit, value). Uses a flag rather than None so that a cached
        empty result still counts as a hit."""
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return False, None
            expires_at, value = entry
            if now >= expires_at:
                del self._data[key]
                self.misses += 1
                return False, None
            self.hits += 1
            return True, value

    def set(self, key: str, value: Any) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._data) >= self.max_entries:
                self._evict(now)
            self._data[key] = (now + self.ttl, value)

    def _evict(self, now: float) -> None:
        """Drop expired entries; if that frees nothing, drop the oldest."""
        expired = [k for k, (exp, _) in self._data.items() if now >= exp]
        for k in expired:
            del self._data[k]
        if not expired and self._data:
            oldest = min(self._data, key=lambda k: self._data[k][0])
            del self._data[oldest]

    def get_or_call(self, key: str, fn: Callable[[], Any]) -> tuple[Any, bool]:
        """Return (value, was_cache_hit). `fn` runs only on a miss.

        Not locked across the call: two concurrent misses may both compute.
        That is the right trade-off here — holding the lock across a network
        call would serialise every tool invocation behind the slowest one.
        """
        hit, value = self.get(key)
        if hit:
            return value, True
        value = fn()
        self.set(key, value)
        return value, False

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": len(self._data),
                "hits": self.hits,
                "misses": self.misses,
                "ttl_seconds": self.ttl,
            }
