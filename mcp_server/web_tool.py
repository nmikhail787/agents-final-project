"""web.search — live web results via SerpApi, rate-limited, cached, allowlisted.

Failure policy: a dead key, a timeout or an exhausted quota must never raise
out of this tool. The MCP process serves rag.search too, and taking the whole
server down because a third-party API had a bad afternoon would fail the demo
on both tools instead of degrading one. Every failure path returns a normal
response with `degraded=true` and an explanation.
"""

import os
import threading
import time
from typing import Optional

from pydantic import BaseModel, Field

from . import providers
from .allowlist import filter_results
from .cache import TTLCache, make_key
from .jsonl_log import log_call

# The brief mandates a 60-300s TTL for live results. 180s sits mid-range: long
# enough that a demo re-run is a cache hit, short enough to stay honest about
# "live" prices.
_TTL_SECONDS = float(os.environ.get("WEB_SEARCH_TTL", "180"))
_CACHE = TTLCache(ttl_seconds=max(60.0, min(_TTL_SECONDS, 300.0)), max_entries=256)

# SerpApi's free tier is metered (250 searches) and shared with the team.
# A hard floor on inter-request spacing protects both the quota and the ToS.
_MIN_INTERVAL = float(os.environ.get("WEB_SEARCH_MIN_INTERVAL", "1.0"))
_rate_lock = threading.Lock()
_last_call_at = 0.0


class RateLimitExceeded(RuntimeError):
    pass


def _throttle() -> None:
    """Block until the minimum inter-request interval has elapsed."""
    global _last_call_at
    with _rate_lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()


class WebResult(BaseModel):
    title: str = Field(description="Result title.")
    url: str = Field(description="Source URL. Cite this for any live claim.")
    snippet: str = Field(description="Result snippet, or retailer and delivery info for shopping hits.")
    price: Optional[str] = Field(
        default=None, description="Listed price as a display string, e.g. '$24.99'. Null for organic results."
    )
    availability: Optional[str] = Field(
        default=None, description="Availability or delivery text when the provider supplies it."
    )


class WebSearchResponse(BaseModel):
    results: list[WebResult]
    count: int
    query: str
    search_type: str = Field(description="'shopping' (price/availability) or 'search' (organic).")
    cached: bool = Field(description="True if served from the TTL cache rather than a live call.")
    cache_ttl_seconds: float
    degraded: bool = Field(description="True if the provider failed and results are empty or mocked.")
    blocked_domains: list[str] = Field(description="Domains dropped by the safety allowlist.")
    notes: list[str]


def run_web_search(
    query: str,
    num: int = 5,
    search_type: str = "shopping",
) -> WebSearchResponse:
    """Synchronous core. Called off the event loop by the server."""
    started = time.perf_counter()
    num = max(1, min(int(num), 20))
    if search_type not in ("shopping", "search"):
        search_type = "shopping"

    request = {"query": query, "num": num, "search_type": search_type}
    cache_key = make_key("web.search", query, num, search_type)
    notes: list[str] = []
    degraded = False
    blocked: list[str] = []

    hit, cached_value = _CACHE.get(cache_key)
    if hit:
        raw = cached_value
        was_hit = True
    else:
        was_hit = False
        try:
            _throttle()
            raw = providers.serpapi_search(query, search_type=search_type, num=num)
            _CACHE.set(cache_key, raw)
        except providers.ProviderError as exc:
            # Degrade, do not raise. rag.search still has to work.
            duration = (time.perf_counter() - started) * 1000
            log_call("web.search", request, error=str(exc), duration_ms=duration)
            return WebSearchResponse(
                results=[],
                count=0,
                query=query,
                search_type=search_type,
                cached=False,
                cache_ttl_seconds=_CACHE.ttl,
                degraded=True,
                blocked_domains=[],
                notes=[
                    f"Live web search unavailable: {exc}",
                    "Answer from the private catalogue only, and tell the user live pricing could not be checked.",
                ],
            )

    allowed, blocked = filter_results(raw)
    if blocked:
        notes.append(f"Filtered {len(blocked)} result(s) from non-allowlisted domains: {', '.join(blocked)}.")

    if os.environ.get("MOCK_WEB_SEARCH", "").strip() in ("1", "true", "yes"):
        degraded = True
        notes.append("MOCK_WEB_SEARCH is enabled: these are fixtures, not live results. Do not present them as real.")

    if not allowed:
        notes.append("No allowlisted live results. Rely on the private catalogue.")

    response = WebSearchResponse(
        results=[WebResult(**r) for r in allowed],
        count=len(allowed),
        query=query,
        search_type=search_type,
        cached=was_hit,
        cache_ttl_seconds=_CACHE.ttl,
        degraded=degraded,
        blocked_domains=blocked,
        notes=notes,
    )

    duration = (time.perf_counter() - started) * 1000
    log_call(
        "web.search",
        request,
        response={"count": response.count, "titles": [r.title for r in response.results]},
        source_urls=[r.url for r in response.results],
        cache_hit=was_hit,
        duration_ms=duration,
    )
    return response
