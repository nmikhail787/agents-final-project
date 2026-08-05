"""rag.search — private catalogue retrieval over the Amazon 2020 toys slice.

This module is an *adapter*, not a retriever. Person A owns retrieval; the
graph reaches the catalogue only through this tool (README.md:61-62).

On `rating` and `ingredients`: the brief specifies both, and neither exists.
The Kaggle sample ships ten 100%-empty columns including Ingredients, and has
no rating column at all (README.md:22-23, docs/DATA.md). They are declared in
the schema and always emitted as null. Not omitted — a consumer diffing against
the brief should see them and see that they are empty. Not fabricated — an
invented rating would flow straight into a cited recommendation.
"""

import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from .cache import TTLCache, make_key
from .jsonl_log import log_call

# The index is static between build_index.py runs, so a short TTL would only
# throw away work. Long, bounded, and independent of web.search's window.
_CACHE = TTLCache(ttl_seconds=900, max_entries=256)


class RagResult(BaseModel):
    """One catalogue product. Keys are always present; missing values are null."""

    doc_id: str = Field(description="Citation id for private-source claims, e.g. 'T00497'. Cite this.")
    sku: str = Field(description="Catalogue SKU (dataset Uniq Id hash, not a retail SKU).")
    title: str = Field(description="Product title.")
    price: float = Field(description="Price in USD.")
    rating: Optional[float] = Field(
        default=None,
        description="ALWAYS null - the source dataset has no rating column. Do not present a rating to the user.",
    )
    brand: Optional[str] = Field(
        default=None,
        description="Approximate: derived from the first token of the title, so it is noisy.",
    )
    ingredients: Optional[str] = Field(
        default=None,
        description="ALWAYS null - the source dataset's Ingredients column is 100% empty.",
    )
    subcategory: Optional[str] = Field(default=None, description="e.g. 'Building Toys', 'Puzzles'.")
    category: str = Field(description="Top-level category; always 'toys & games'.")
    features: str = Field(description="Product feature text, used as grounding evidence.")
    url: str = Field(description="Public product URL.")
    score: float = Field(description="Relevance 0-1, higher is better.")


class RagSearchResponse(BaseModel):
    results: list[RagResult]
    count: int = Field(description="Number of results returned.")
    query: str
    filters_applied: dict[str, Any] = Field(description="Filters actually applied, after validation.")
    unavailable_fields: list[str] = Field(
        description="Fields the brief requires that have no source in this corpus and are always null.",
    )
    notes: list[str] = Field(description="Human-readable caveats for the answering agent.")


UNAVAILABLE_FIELDS = ["rating", "ingredients"]


def _clean_filters(
    max_price: Optional[float],
    min_price: Optional[float],
    subcategory: Optional[str],
    brand: Optional[str],
) -> dict[str, Any]:
    """Drop unset filters. Person A's _build_where treats any present key as a
    hard constraint, so passing None through would over-constrain the query."""
    out: dict[str, Any] = {}
    if max_price is not None:
        out["max_price"] = float(max_price)
    if min_price is not None:
        out["min_price"] = float(min_price)
    if subcategory:
        out["subcategory"] = subcategory
    if brand:
        out["brand"] = brand
    return out


def _to_result(row: dict[str, Any]) -> RagResult:
    """Map Person A's Product dict onto the brief's result shape."""
    return RagResult(
        doc_id=row["doc_id"],
        sku=row["sku"],
        title=row["title"],
        price=row["price"],
        rating=None,        # no source in corpus
        brand=row["brand"],
        ingredients=None,   # no source in corpus
        subcategory=row["subcategory"],
        category=row["category"],
        features=row["features"],
        url=row["url"],
        score=row["score"],
    )


def run_rag_search(
    query: str,
    k: int = 5,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    subcategory: Optional[str] = None,
    brand: Optional[str] = None,
) -> RagSearchResponse:
    """Synchronous core. Called off the event loop by the server."""
    started = time.perf_counter()
    k = max(1, min(int(k), 25))
    filters = _clean_filters(max_price, min_price, subcategory, brand)

    request = {"query": query, "k": k, "filters": filters}
    cache_key = make_key("rag.search", query, k, filters)

    def _do_search() -> list[dict[str, Any]]:
        # Imported lazily so an unbuilt index surfaces as a tool-level error
        # rather than killing the server at startup.
        from retrieval import search

        return search(query, filters, k=k)

    try:
        rows, was_hit = _CACHE.get_or_call(cache_key, _do_search)
    except Exception as exc:
        duration = (time.perf_counter() - started) * 1000
        log_call("rag.search", request, error=str(exc), duration_ms=duration)
        raise

    notes: list[str] = []
    if not rows:
        notes.append(
            "No products matched. Filters are hard constraints - nothing was relaxed. "
            "Tell the user nothing matched rather than suggesting a near miss."
        )
    notes.append("rating and ingredients are null for every row: absent from the source dataset.")

    response = RagSearchResponse(
        results=[_to_result(r) for r in rows],
        count=len(rows),
        query=query,
        filters_applied=filters,
        unavailable_fields=list(UNAVAILABLE_FIELDS),
        notes=notes,
    )

    duration = (time.perf_counter() - started) * 1000
    log_call(
        "rag.search",
        request,
        response={"count": response.count, "doc_ids": [r.doc_id for r in response.results]},
        source_urls=[r.url for r in response.results],
        cache_hit=was_hit,
        duration_ms=duration,
    )
    return response
