"""Private catalog retrieval over the Amazon Product Dataset 2020 (Toys & Games slice).

Owner: Person A.
Consumed by: the MCP server's rag.search tool.

Contract note: every key in Product is always present on every record.
Missing values are None, never absent. Do not rely on .get() defaults.
"""

from typing import TypedDict, Optional

import chromadb

_CLIENT = chromadb.PersistentClient(path="chroma")
_COL = _CLIENT.get_collection("products")

OVERFETCH = 60


class Product(TypedDict):
    doc_id: str          # citation id, e.g. "T00001"
    sku: str
    title: str
    brand: Optional[str]
    price: float
    subcategory: Optional[str]
    category: str
    features: str
    url: str
    score: float         # relevance, 0-1, higher is better


def _build_where(filters: dict):
    clauses = []
    if filters.get("max_price") is not None:
        clauses.append({"price": {"$lte": float(filters["max_price"])}})
    if filters.get("min_price") is not None:
        clauses.append({"price": {"$gte": float(filters["min_price"])}})
    if filters.get("subcategory"):
        clauses.append({"subcategory": {"$eq": filters["subcategory"]}})
    if filters.get("brand"):
        clauses.append({"brand": {"$eq": filters["brand"]}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def search(query: str, filters: dict = None, k: int = 10) -> list[Product]:
    """Hybrid retrieval: vector similarity + hard metadata filters.

    filters keys (all optional):
        max_price: float
        min_price: float
        subcategory: str   e.g. "Building Toys", "Puzzles"
        brand: str

    Filters are HARD constraints. A product over max_price is never returned,
    regardless of semantic similarity. Returns [] when nothing matches rather
    than relaxing a constraint.
    """
    filters = filters or {}

    res = _COL.query(
        query_texts=[query],
        n_results=min(OVERFETCH, _COL.count()),
        where=_build_where(filters),
    )

    metas = res["metadatas"][0]
    dists = res["distances"][0]

    out: list[Product] = []
    for m, d in zip(metas, dists):
        out.append({
            "doc_id": m["doc_id"],
            "sku": m["sku"],
            "title": m["title"],
            "brand": m["brand"] or None,
            "price": m["price"],
            "subcategory": m["subcategory"] or None,
            "category": m["category"],
            "features": m["features"],
            "url": m["url"],
            "score": round(1.0 / (1.0 + d), 4),
        })
    return out[:k]


if __name__ == "__main__":
    tests = [
        ("building set for a seven year old", {"max_price": 30}),
        ("jigsaw puzzle for adults", {}),
        ("soft plush animal for a toddler", {"max_price": 20}),
        ("science experiment kit", {"max_price": 50}),
        ("board game for family game night", {"min_price": 10, "max_price": 40}),
        ("lego", {"brand": "LEGO"}),
        ("anything at all", {"max_price": 0.25}),   # expect []
    ]
    for q, f in tests:
        hits = search(q, f, k=3)
        print(f"\n=== {q!r}  filters={f}  -> {len(hits)} hits")
        for h in hits:
            print(f"  ${h['price']:>7.2f}  {h['score']:.3f}  [{h['subcategory']}]  {h['title'][:70]}")