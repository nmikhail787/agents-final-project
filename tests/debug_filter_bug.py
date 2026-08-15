"""
Bug repro: rag.search / web.search do not appear to enforce max_price,
min_price, brand, and subcategory filters (filters_applied comes back {}
and out-of-range/mismatched items are still returned).

Run with:  python debug_filter_bug.py
In terminal
"""

import asyncio
import json
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["-m", "mcp_server.server"],
    cwd=os.getcwd(),
)


async def run_case(session, tool_name, query, filters, label):
    print(f"\n{'='*70}")
    print(f"CASE: {label}")
    print(f"Tool: {tool_name}")
    print(f"Query: {query!r}")
    print(f"Filters sent: {filters}")
    print(f"{'-'*70}")

    result = await session.call_tool(tool_name, arguments={"query": query, "filters": filters})

    # print the raw, unparsed response exactly as the server sent it
    raw_text = result.content[0].text
    print("RAW RESPONSE:")
    print(raw_text)

    # also pretty-print just the bits relevant to the bug
    parsed = json.loads(raw_text)
    print(f"{'-'*70}")
    print(f"filters_applied returned: {parsed.get('filters_applied')}")
    if "results" in parsed:
        for item in parsed["results"]:
            price = item.get("price")
            brand = item.get("brand")
            subcat = item.get("subcategory")
            print(f"  - {item.get('title', '')[:60]:60}  price={price}  brand={brand}  subcategory={subcat}")


async def main():
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Connected to MCP server.")

            # CASE 1: max_price should exclude anything over $30
            await run_case(
                session, "rag.search",
                query="building set",
                filters={"max_price": 30},
                label="rag.search with max_price=30 (expect: no result over $30)",
            )

            # CASE 2: brand should exclude anything not LEGO
            await run_case(
                session, "rag.search",
                query="building set",
                filters={"brand": "LEGO"},
                label="rag.search with brand=LEGO (expect: only brand == 'LEGO')",
            )

            # CASE 3: subcategory should restrict to Building Toys only
            await run_case(
                session, "rag.search",
                query="toy",
                filters={"subcategory": "Building Toys"},
                label="rag.search with subcategory='Building Toys' (expect: only that subcategory)",
            )

            # CASE 4: min_price should exclude anything under $20
            await run_case(
                session, "rag.search",
                query="toy",
                filters={"min_price": 20},
                label="rag.search with min_price=20 (expect: no result under $20)",
            )

    print(f"\n{'='*70}")
    print("Done. Compare 'Filters sent' vs 'filters_applied returned' vs the")
    print("actual price/brand/subcategory values printed for each result above.")


if __name__ == "__main__":
    asyncio.run(main())