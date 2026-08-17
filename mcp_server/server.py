"""MCP server exposing the project's two tools over stdio.

    rag.search   private Chroma catalogue (Amazon 2020 toys slice)
    web.search   live web results via SerpApi

Run directly:      python -m mcp_server.server
Inspect:           npx @modelcontextprotocol/inspector python -m mcp_server.server

Exactly two tools are registered, matching the brief. Diagnostics ride along in
each response (`cached`, `degraded`, `notes`) rather than as a third tool.
"""

import sys
from pathlib import Path
from typing import Any, Optional

# Person A's retrieval.py lives at the repo root. Inspector launches this
# server with an arbitrary cwd, so put the repo root on the path explicitly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import anyio

# The SDK renamed its high-level server class in 2.0 (FastMCP -> MCPServer) and
# moved the module. Support both deliberately: installing the LangGraph/OpenAI
# dependency tree can silently downgrade mcp from 2.x to 1.x, and a server that
# will not import scores zero no matter whose install broke the pin. The .tool()
# and .run() signatures are identical across both; only the version kwarg differs.
try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _ServerClass

    _SERVER_KWARGS = {"version": "0.1.0"}
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _ServerClass

    _SERVER_KWARGS = {}  # FastMCP.__init__ takes no version kwarg

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:  # python-dotenv is pinned, but do not hard-fail on it
    pass

# ORDER MATTERS - do not let an import sorter hoist these above load_dotenv().
# web_tool reads WEB_SEARCH_TTL at import time to size its cache, and rag_tool's
# provider reads the API key. Loading .env after these imports would silently
# make every .env setting a no-op.
# isort: off
from mcp_server.rag_tool import RagSearchResponse, run_rag_search  # noqa: E402
from mcp_server.web_tool import WebSearchResponse, run_web_search  # noqa: E402

# isort: on

server = _ServerClass(
    name="product-discovery",
    **_SERVER_KWARGS,
    instructions=(
        "Product discovery over a private Amazon 2020 toys catalogue.\n\n"
        "Prefer rag.search for product facts; it returns doc_id values which are the "
        "citation handles for private claims. Call web.search only when the user asks "
        "about current price, availability, or the latest offers.\n\n"
        "This corpus has NO ratings and NO ingredients. Never present either to the user."
    ),
)


@server.tool(
    name="rag.search",
    title="Private catalogue search",
    description=(
        "Vector search with hard metadata filters over the private Amazon 2020 "
        "toys catalogue (6,461 products). Returns products with a doc_id that MUST "
        "be used as the citation for any private-source claim.\n\n"
        "Filters are HARD constraints: a product above max_price is never returned, "
        "and no constraint is ever relaxed. An empty result means nothing matched - "
        "say so rather than offering a near miss.\n\n"
        "rating and ingredients are always null: the source dataset has no rating "
        "column and its Ingredients column is entirely empty. Do not surface them.\n\n"
        "Note: brand is approximate (first token of the title), so brand filtering is "
        "unreliable. Prefer max_price and subcategory. Age constraints are NOT "
        "supported - age appears in only 2.4% of product text.\n\n"
        "Filters may be passed EITHER nested as filters={'max_price': 30} OR as flat "
        "arguments (max_price=30). Both are equivalent; flat wins on conflict. Check "
        "the filters_applied field in the response to confirm what was actually used - "
        "it is a RESPONSE field, not an input parameter."
    ),
)
async def rag_search(
    query: str,
    k: int = 5,
    filters: Optional[dict[str, Any]] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    subcategory: Optional[str] = None,
    brand: Optional[str] = None,
) -> RagSearchResponse:
    """Search the private product catalogue.

    Args:
        query: Natural-language description of the product wanted.
        k: Maximum products to return (1-25).
        filters: Nested filter dict, e.g. {"max_price": 30, "subcategory": "Puzzles"}.
            Accepts the same four keys as the flat arguments below.
        max_price: Hard upper bound in USD. Overrides filters["max_price"].
        min_price: Hard lower bound in USD. Overrides filters["min_price"].
        subcategory: Exact subcategory, e.g. "Building Toys", "Puzzles".
        brand: Exact brand match. Unreliable - see the tool description.
    """
    # Chroma query is blocking and does disk I/O; keep it off the event loop.
    return await anyio.to_thread.run_sync(
        lambda: run_rag_search(query, k, max_price, min_price, subcategory, brand, filters)
    )


@server.tool(
    name="web.search",
    title="Live web search",
    description=(
        "Live web search via the SerpApi API, for current price and availability "
        "that the private catalogue cannot supply. Results are rate-limited, cached "
        "with a 60-300s TTL, and filtered against a domain allowlist.\n\n"
        "Use search_type='shopping' (default) for price and availability; use "
        "'search' for general organic results.\n\n"
        "If the provider is unavailable this returns degraded=true with an empty "
        "result list rather than failing. When that happens, answer from the private "
        "catalogue and tell the user live pricing could not be checked. Cite the url "
        "of any live result you use."
    ),
)
async def web_search(
    query: str,
    num: int = 5,
    search_type: str = "shopping",
) -> WebSearchResponse:
    """Search the live web for price and availability.

    Args:
        query: Search query, typically a product title.
        num: Maximum results to return (1-20).
        search_type: "shopping" for price/availability, or "search" for organic.
    """
    return await anyio.to_thread.run_sync(lambda: run_web_search(query, num, search_type))


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
