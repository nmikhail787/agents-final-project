"""Web-search provider clients.

SerpApi is the primary provider: the project has an account with a 250-search
free allowance, and its google_shopping engine returns price, delivery and
merchant directly — which is exactly the optional price?/availability? fields
the brief asks for.

Note for anyone extending this: SerpApi (serpapi.com) and Serper (serper.dev)
are different companies with different APIs. SerpApi takes a GET with the key
as an `api_key` query parameter; Serper takes a POST with an `X-API-KEY`
header. A key from one returns 403 against the other.

Everything provider-specific lives behind `serpapi_search()`, so swapping
providers means writing one more function with the same return shape.

MOCK_WEB_SEARCH=1 serves fixtures instead of calling the network. The free tier
is metered and small, so the default development path must not spend searches.
"""

import logging
import os
from typing import Any

import httpx

# SerpApi authenticates with an `api_key` QUERY PARAMETER, and httpx logs full
# request URLs at INFO. On a stdio server that goes to stderr, which the MCP
# Inspector renders in its log pane — i.e. the API key would be on screen during
# the demo. Silence httpx's request log; ours in jsonl_log.py is the audit trail
# and it never sees the key.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"


def _redact_url(url: str) -> str:
    """Strip the api_key from a URL before it can reach any message or log."""
    key = _api_key()
    return url.replace(key, "***REDACTED***") if key else url

# SerpApi selects behaviour by `engine`, not by a different URL path.
ENGINES = {
    "shopping": "google_shopping",
    "search": "google",
}

DEFAULT_TIMEOUT = 15.0


class ProviderError(RuntimeError):
    """Provider failed in a way the tool should report, not crash on."""


def _normalise_organic(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title") or "",
        "url": item.get("link") or "",
        "snippet": item.get("snippet") or "",
        "price": None,
        "availability": None,
    }


def _extensions_text(item: dict[str, Any]) -> str:
    """`extensions` is a list of badge strings, e.g. ['Free delivery', 'In stock']."""
    ext = item.get("extensions")
    if isinstance(ext, list):
        return ", ".join(str(e) for e in ext if e)
    return ""


def _normalise_shopping(item: dict[str, Any]) -> dict[str, Any]:
    """Shopping hits carry price and merchant; organic hits do not.

    Merchant, rating and badges are folded into the snippet: the brief's result
    shape has no field for them, and merchant + rating are the most useful
    signals the downstream reconciliation step has for matching a live listing
    to a catalogue product.
    """
    bits: list[str] = []
    if item.get("source"):
        bits.append(str(item["source"]))
    if item.get("rating"):
        reviews = item.get("reviews")
        bits.append(f"{item['rating']}★" + (f" ({reviews} reviews)" if reviews else ""))
    if item.get("snippet"):
        bits.append(str(item["snippet"]))
    extensions = _extensions_text(item)
    if extensions:
        bits.append(extensions)

    return {
        "title": item.get("title") or "",
        # google_shopping returns `link: null` on every row; product_link (a
        # Google Shopping product page) is the only URL available. The merchant
        # name lives in `source` and is carried in the snippet.
        "url": item.get("product_link") or item.get("link") or "",
        "snippet": " · ".join(bits) or (item.get("title") or ""),
        "price": item.get("price"),
        "availability": extensions or None,
    }


def _mock_results(query: str, search_type: str) -> list[dict[str, Any]]:
    """Deterministic fixtures. Clearly labelled so they can never be mistaken
    for live data in a transcript or a demo."""
    return [
        {
            "title": f"[MOCK] {query} - Amazon.com",
            "url": "https://www.amazon.com/dp/B00MOCK001",
            "snippet": "Mock result served because MOCK_WEB_SEARCH=1. No network call was made.",
            "price": "$24.99" if search_type == "shopping" else None,
            "availability": "In stock" if search_type == "shopping" else None,
        },
        {
            "title": f"[MOCK] {query} - Walmart",
            "url": "https://www.walmart.com/ip/000000000",
            "snippet": "Mock result served because MOCK_WEB_SEARCH=1. No network call was made.",
            "price": "$22.47" if search_type == "shopping" else None,
            "availability": "Pickup today" if search_type == "shopping" else None,
        },
    ]


# The literal placeholders shipped in .env.example. Treated as "no key set" so
# a teammate who copied the file but never filled it in gets a useful message
# instead of a bare 401 from the provider.
_PLACEHOLDER_KEYS = frozenset(
    {"your-serpapi-key-here", "your-serper-key-here", "your-key-here", "changeme"}
)


def _api_key() -> str:
    """SERPAPI_API_KEY, falling back to the older SERPER_API_KEY name so an
    existing .env keeps working."""
    key = (
        os.environ.get("SERPAPI_API_KEY", "").strip()
        or os.environ.get("SERPER_API_KEY", "").strip()
    )
    return "" if key.lower() in _PLACEHOLDER_KEYS else key


def serpapi_search(
    query: str,
    search_type: str = "shopping",
    num: int = 10,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Call SerpApi and return normalised results.

    Raises ProviderError on any failure the caller should surface as a degraded
    response rather than a crash.
    """
    if os.environ.get("MOCK_WEB_SEARCH", "").strip() in ("1", "true", "yes"):
        return _mock_results(query, search_type)

    api_key = _api_key()
    if not api_key:
        raise ProviderError(
            "SERPAPI_API_KEY is not set. Copy .env.example to .env and add your key, "
            "or set MOCK_WEB_SEARCH=1 to run against fixtures."
        )

    engine = ENGINES.get(search_type)
    if engine is None:
        raise ProviderError(
            f"unknown search_type {search_type!r}; expected 'search' or 'shopping'"
        )

    params = {
        "engine": engine,
        "q": query,
        "api_key": api_key,
        "num": max(1, min(num, 20)),
    }

    try:
        resp = httpx.get(SERPAPI_ENDPOINT, params=params, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderError(f"serpapi timed out after {timeout}s") from exc
    except httpx.HTTPError as exc:
        # httpx error strings embed the request URL, which carries the api_key.
        raise ProviderError(f"serpapi request failed: {_redact_url(str(exc))}") from exc

    if resp.status_code == 401:
        raise ProviderError("serpapi rejected the API key (401)")
    if resp.status_code == 429:
        raise ProviderError("serpapi rate limit / search allowance exhausted (429)")
    if resp.status_code >= 400:
        raise ProviderError(f"serpapi returned HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise ProviderError("serpapi returned a non-JSON body") from exc

    # SerpApi reports some failures as HTTP 200 with an `error` key.
    if isinstance(payload, dict) and payload.get("error"):
        raise ProviderError(f"serpapi error: {payload['error']}")

    # SerpApi's google_shopping engine ignores `num` and returns ~40 rows, so
    # the caller's limit has to be applied here or every response is oversized.
    limit = max(1, min(num, 20))
    if search_type == "shopping":
        rows = [_normalise_shopping(i) for i in payload.get("shopping_results", [])]
    else:
        rows = [_normalise_organic(i) for i in payload.get("organic_results", [])]
    return rows[:limit]


# Backwards-compatible alias: web_tool.py called this before the provider
# switch, and keeping the old name costs nothing.
serper_search = serpapi_search
