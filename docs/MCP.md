# MCP Server — tool schemas and safety notes

Owner: Person B. One MCP server, two tools, stdio transport.

| Tool | Purpose | Source |
|---|---|---|
| `rag.search` | Private catalogue retrieval (6,461 Amazon 2020 toys) | Chroma index via `retrieval.search` |
| `web.search` | Live price and availability | SerpApi (google_shopping) |

---

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env          # add your SERPAPI_API_KEY
python build_index.py         # builds chroma/ — required before rag.search works
./run_mcp.sh                  # or: python -m mcp_server.server
```

Inspect it:

```bash
npx @modelcontextprotocol/inspector python -m mcp_server.server
```

Test it:

```bash
pytest tests/ -q      # 43 tests, no network — the provider is monkeypatched
```

The suite deliberately spends no SerpApi quota. It covers TTL expiry and
clamping, secret redaction, the domain allowlist, provider normalisation
(including the `num`-ignored and `link: null` quirks), degradation on a dead
key, and the always-null `rating`/`ingredients` contract.

> **Do not run `./run_index.sh`.** Its first step rebuilds the parquet from the
> raw Kaggle CSV, which is gitignored and not in the repo, so `set -e` aborts the
> whole script. `data/products.parquet` is already committed — you only need
> `python build_index.py`.

---

## Transport and discovery

- **Transport:** stdio (the brief allows stdio or streamable HTTP/SSE).
- **Server name:** `product-discovery`, version `0.1.0`.
- **Discovery:** standard `tools/list`. Both tools expose a JSON Schema for
  input *and* output, generated from Pydantic models so the schema cannot drift
  from the implementation.
- Tool names contain a dot (`rag.search`, `web.search`) as the brief specifies.
  Verified accepted by the Python SDK and Inspector.

---

## `rag.search`

Vector search with hard metadata filters over the private catalogue.

### Input

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | string | *required* | Natural-language product description. |
| `k` | integer | 5 | Clamped to 1–25. |
| `max_price` | number \| null | null | Hard upper bound, USD. |
| `min_price` | number \| null | null | Hard lower bound, USD. |
| `subcategory` | string \| null | null | Exact match, e.g. `"Building Toys"`, `"Puzzles"`. |
| `brand` | string \| null | null | Exact match. Unreliable — see caveats. |

### Output

```jsonc
{
  "results": [
    {
      "doc_id": "T00497",        // CITE THIS for private-source claims
      "sku": "66d49bbe...",      // dataset Uniq Id hash, not a retail SKU
      "title": "Melissa & Doug Wooden Construction Building Set...",
      "price": 16.99,
      "rating": null,            // ALWAYS null — see "Fields with no source"
      "brand": "Melissa",        // approximate, first token of title
      "ingredients": null,       // ALWAYS null — see "Fields with no source"
      "subcategory": "Building Toys",
      "category": "toys & games",
      "features": "...",         // grounding evidence
      "url": "https://www.amazon.com/...",
      "score": 0.62              // relevance 0-1, higher is better
    }
  ],
  "count": 1,
  "query": "building set for a seven year old",
  "filters_applied": { "max_price": 30.0 },
  "unavailable_fields": ["rating", "ingredients"],
  "notes": ["rating and ingredients are null for every row: absent from the source dataset."]
}
```

### Caveats that affect the graph and the UI

- **Filters are hard constraints.** A $40 item is never returned for a `max_price: 30`
  query regardless of similarity. Nothing is ever relaxed.
- **`count: 0` means nothing matched.** Say so. Do not offer a near miss — that
  produces an ungrounded recommendation.
- **`brand` is approximate**, derived from the first token of the product title
  (`build_catalog.py:21-29`). Filtering by brand is unreliable; prefer
  `max_price` and `subcategory`.
- **Age constraints are not supported.** Age appears in 2.4% of product text and
  the eval confirms age qualifiers degrade results. The Router should ignore age.
  The canonical demo query — *"a building set for a seven-year-old under thirty
  dollars"* — is answered on price alone, and that is intended.

### Fields with no source

The brief specifies `rating` and `ingredients`. Neither exists in this corpus:
the Kaggle sample ships ten 100%-empty columns including `Ingredients`, and has
no rating column at all (`README.md:22-23`, `docs/DATA.md`).

They are **declared in the schema and always emitted as `null`** — not omitted,
so a consumer diffing against the brief can see they exist and see they are
empty; and not fabricated, because an invented rating would flow straight into a
cited recommendation. `unavailable_fields` states this per-response so the
Answerer can react programmatically rather than by parsing prose.

---

## `web.search`

Live web results via SerpApi, for the price and availability the private
catalogue cannot supply.

### Input

| Param | Type | Default | Notes |
|---|---|---|---|
| `query` | string | *required* | Typically a product title. |
| `num` | integer | 5 | Clamped to 1–20. |
| `search_type` | string | `"shopping"` | `"shopping"` for price/availability, `"search"` for organic. |

### Output

```jsonc
{
  "results": [
    {
      "title": "LEGO Classic Medium Creative Brick Box",
      "url": "https://www.google.com/search?ibp=oshop&q=...",  // CITE THIS for live claims
      "snippet": "LEGO.com · 4.8★ (13000 reviews) · Also nearby",
      "price": "$34.99",         // display string, null for organic results
      "availability": "Also nearby"
    }
  ],
  "count": 1,
  "query": "...",
  "search_type": "shopping",
  "cached": false,              // true = served from TTL cache, not a live call
  "cache_ttl_seconds": 180.0,
  "degraded": true,             // true = provider failed OR fixtures are on
  "blocked_domains": ["example.com"],
  "notes": ["..."]
}
```

### Failure behaviour

A dead key, a timeout, or an exhausted quota **never raises**. The tool returns
`degraded: true`, `results: []`, and a `notes` entry explaining what happened.
This is deliberate: the same process serves `rag.search`, and letting a
third-party outage kill the server would fail both tools instead of degrading
one. When `degraded` is true, answer from the private catalogue and tell the
user live pricing could not be checked.

### Provider quirks worth knowing

- **URLs are Google Shopping product pages**, not merchant deep links. SerpApi's
  `google_shopping` engine returns `link: null` on every row; `product_link` is
  the only URL available. The merchant name is carried in the snippet
  (`"LEGO.com · 4.8★ (13000 reviews)"`). The links resolve to the product, so
  they are usable citations — they just are not merchant URLs.
- **`num` is enforced by this server, not by SerpApi.** The shopping engine
  ignores it and returns ~40 rows regardless, so `providers.py` truncates.
  Without that, every response was 40 items wide.
- **Live ratings exist here, and they are not catalogue ratings.** Shopping
  results carry a real star rating and review count, which get folded into the
  snippet. `rag.search.rating` is *always null* and refers to the private
  corpus. Do not present a live web rating as though it were a rating for the
  catalogue product — they are different products from different sources, and
  conflating them is exactly the sort of ungrounded claim the Critic should
  catch. If you surface a live rating, cite the web `url` for it.

---

## Caching

Two instances of one `TTLCache` (`mcp_server/cache.py`), because the tools have
different staleness semantics:

| Tool | TTL | Why |
|---|---|---|
| `web.search` | **180s** (configurable 60–300, clamped) | Live prices. The brief mandates this window. Mid-range: long enough that a demo re-run is a cache hit, short enough to stay honest about "live". |
| `rag.search` | 900s | The Chroma index is static between `build_index.py` runs, so a short TTL would only throw away work. |

Keys are the tool name plus canonicalised arguments (`sort_keys=True`), so
argument ordering does not cause a spurious miss. The cache is in-process and
in-memory: restarting the server clears it.

No new dependency. `cachetools` is *not* in `requirements.txt` — it only exists
in the local anaconda env as a transitive dep of something else, so relying on it
would work on one machine and break in a clean venv.

## Rate limiting

`web.search` enforces a minimum interval between live provider calls
(`WEB_SEARCH_MIN_INTERVAL`, default 1.0s), protecting both the metered free tier
and the provider's ToS. Cache hits bypass the throttle entirely.

---

## Logging

Append-only JSONL at `logs/mcp_requests.jsonl` (gitignored — it contains full
user query text). One object per line:

```jsonc
{
  "timestamp": "2026-08-05T16:31:23.451+00:00",
  "tool": "rag.search",
  "request": {"query": "...", "k": 3, "filters": {"max_price": 30.0}},
  "response": {"count": 3, "doc_ids": ["T00497", "T02465", "T02153"]},
  "source_urls": ["https://www.amazon.com/..."],
  "cache_hit": false,
  "duration_ms": 624.09,
  "error": null
}
```

Covers the brief's four required elements: request, response, timestamp, source
URL. **No secrets:** any key whose name contains `key`, `token`, `secret`,
`password`, `authorization` or `api_key` is replaced with `***REDACTED***` before
the line is written, and long strings are truncated so one `features` blob cannot
dominate the file. Logging failures are swallowed — the audit trail must never
break the call it is describing.

---

## Safety notes

**Domain allowlist.** `web.search` results are filtered against an allowlist of
mainstream retailers and price aggregators (`mcp_server/allowlist.py`).
Non-allowlisted domains are dropped and reported in `blocked_domains` rather than
silently discarded — an invisible filter is impossible to debug or demo.
Override with `WEB_SEARCH_ALLOWLIST` (comma-separated) to replace the default.

**robots.txt and ToS.** To be precise about what this server does: it does not
crawl. It calls SerpApi, a licensed commercial interface to search results, and
returns only the metadata that API hands back. We never fetch a product page
ourselves, so there is no crawl for robots.txt to govern. What we do owe is the
SerpApi ToS — stay inside the rate limit and do not cache beyond the freshness
window — and both are enforced in code (see Caching and Rate limiting above). If
this server is ever extended to fetch pages directly, a robots.txt check becomes
mandatory at that point.

**Secrets.** The API key is read from `.env` (gitignored) via `python-dotenv`.
It never appears in code, in tool output, or in the audit log.

One trap worth knowing if you touch `providers.py`: SerpApi authenticates with an
`api_key` **query parameter**, not a header, so the key is part of every request
URL. `httpx` logs full request URLs at INFO level, and on a stdio server that
goes to stderr — which the MCP Inspector renders in its log pane, putting the key
on screen during a demo. `providers.py` therefore pins the `httpx`/`httpcore`
loggers to WARNING and redacts the key out of any exception string before it can
reach a response. If you swap in a provider that authenticates by header, this
stops being a concern — but do not remove the redaction while SerpApi is in use.

**Unsafe advice.** Out of scope for a toys catalogue, but the corpus carries no
ingredient data at all, so the Answerer has no basis on which to give chemical or
safety guidance and should decline if asked.

---

## For Person C (LangGraph)

Launch config:

```jsonc
{
  "command": "python",
  "args": ["-m", "mcp_server.server"],
  "cwd": "<repo root>"
}
```

Contract points that affect your nodes:

- **Citations:** `rag.search` → cite `doc_id` (e.g. `T00497`). `web.search` →
  cite `url`. Every private claim needs a `doc_id`.
- **Planner rule:** prefer `rag.search` for product facts; also call `web.search`
  when the user says *current price*, *availability*, *now*, or *latest*.
- **Reconciliation:** match `rag.search` results to `web.search` results on title
  similarity. `RapidFuzz` is already in `requirements.txt:89`. Do not match on
  `sku` — ours is a dataset hash, not a retail identifier, so it will never
  match a live listing.
- **Never present `rating` or `ingredients`.** They are always `null`. Check
  `unavailable_fields` if you want to assert this programmatically.
- **Handle `count: 0` and `degraded: true` explicitly.** Both are normal
  responses, not errors.
