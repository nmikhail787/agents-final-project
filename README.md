# Voice-to-Voice Product Discovery Assistant

Agentic voice assistant for product discovery: speak a request, a LangGraph
pipeline routes it, retrieves grounded evidence from a private catalog and
optionally the live web via MCP, and answers by TTS with on-screen citations.

## You need your own API key

The `web.search` MCP tool calls **SerpApi**. Everyone runs their own key — none
is committed, and `.env` is gitignored.

1. Sign up at **https://serpapi.com** (free plan, 250 searches/month, no card).
2. Copy your key from the *API Key* page in the dashboard.
3. `cp .env.example .env` and set `SERPAPI_API_KEY=<your key>`.

> SerpApi (serpapi.com) and Serper (serper.dev) are **different services** with
> incompatible APIs. A Serper key returns `403 Unauthorized` here. This project
> targets SerpApi.

No key yet? Set `MOCK_WEB_SEARCH=1` in `.env` and `web.search` serves labelled
fixtures instead, so the rest of the pipeline still runs. `rag.search` needs no
key at all — it is entirely local.

## Lanes

| Person | Owns | Status |
|---|---|---|
| A | Data + retrieval (`retrieval.py`, Chroma index) | Done — working against real data |
| B | MCP server (`web.search`, `rag.search`) | Done — two tools on stdio, see [`docs/MCP.md`](docs/MCP.md) |
| C | LangGraph orchestration (router / planner / retriever / answerer) | |
| D | Voice (Whisper + TTS) and Streamlit UI | |

## IMPORTANT: the corpus changed from the brief

The project brief suggests a Household Cleaning slice. **That slice does not
exist in this dataset** — `Health & Household` has 23 rows. We are using
**Toys & Games**: 6,461 products after cleaning and dedup.

Ten columns in the Kaggle sample ship 100% empty, including `Brand Name`,
`Ingredients`, `Asin`, and `List Price`. There is no rating column at all.

Consequences for everyone:

- **No rating, no ingredients, no price-per-unit.** Do not build UI columns,
  prompts, or comparison criteria around them.
- Filters are `max_price`, `min_price`, `subcategory`, `brand`.
- **Do not extract age constraints.** "Something for a five-year-old" is the
  most natural thing a user will say to a toy assistant, and our data cannot
  support it — age appears in 2.4% of product text. The eval confirms age
  qualifiers degrade results. Router should ignore age.
- Demo query: *"a building set for a seven-year-old under thirty dollars"*
  (age is ignored, price is honoured).

Full detail in [`docs/DATA.md`](docs/DATA.md).

## The retrieval contract — stable, code against this

```python
from retrieval import search

search(query: str, filters: dict = None, k: int = 10) -> list[Product]
```

Filters, all optional: `max_price`, `min_price`, `subcategory`, `brand`.

`Product` keys, always present, `None` when missing:
`doc_id`, `sku`, `title`, `brand`, `price`, `subcategory`, `category`,
`features`, `url`, `score`.

Behaviour guarantees:

- Filters are **hard constraints**. A $40 item is never returned for a "$30 max"
  query regardless of semantic similarity.
- Returns `[]` when nothing matches rather than relaxing a constraint. Handle
  the empty case — inventing a near-match produces ungrounded answers.
- `doc_id` (e.g. `T00497`) is the citation id for private-source claims.

**Person B:** expose this as the MCP `rag.search` tool by importing `search`.
Do not reimplement it — the graph should reach the catalog only through MCP.

**Calling it through MCP:** the `rag.search` tool accepts filters *either* nested
as `filters={"max_price": 30}` (the shape above) *or* as flat arguments
(`max_price=30`). Both are equivalent. Always check the response's
`filters_applied` field — the MCP SDK silently drops arguments that aren't in a
tool's schema, so a misnamed filter looks like a successful unfiltered search.
See [`docs/MCP.md`](docs/MCP.md) for a worked example.

## Retrieval quality

Measured over 20 hand-labelled queries (`eval/labeled.csv`):

| Metric | Value |
|---|---|
| hit rate @1 | 85% |
| hit rate @3 | 100% |
| mean precision @3 | 0.83 |

Known failure modes are documented in `docs/DATA.md` — "art supplies for
painting", "outdoor water toys", and age-qualified queries each score 0.33.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Download `promptcloud/amazon-product-dataset-2020` from Kaggle, put the CSV in
`data/raw/`, then:

```bash
./run_index.sh
```

This builds `data/products.parquet`, the Chroma index in `chroma/`, and runs a
retrieval smoke test. Neither the raw CSV nor the index is committed.

**You almost certainly do not need that.** `data/products.parquet` *is*
committed, and `run_index.sh` starts by rebuilding it from the raw CSV — which is
gitignored, so on a fresh clone step 1 fails and `set -e` aborts the script. To
get a working index from what is already in the repo:

```bash
python build_index.py     # ~3 min: downloads the ONNX embedding model, embeds 6,461 docs
```

Do this on good wifi well before any demo — the first run pulls an ~80 MB model
into `~/.cache/chroma`. Once cached, later runs are offline.

## The MCP server — how the graph reaches the tools

Two tools on stdio. Full schemas, caching, logging and safety notes in
[`docs/MCP.md`](docs/MCP.md).

```bash
cp .env.example .env      # add SERPAPI_API_KEY
python build_index.py     # required before rag.search works
./run_mcp.sh              # or: python -m mcp_server.server

npx @modelcontextprotocol/inspector python -m mcp_server.server
```

| Tool | Returns | Cite |
|---|---|---|
| `rag.search` | private catalogue products | `doc_id` |
| `web.search` | live price / availability | `url` |

`rating` and `ingredients` are declared in the `rag.search` schema because the
brief specifies them, but are **always `null`** — see the corpus note above.
Each response carries `unavailable_fields` saying so explicitly.

## Repo layout

```
retrieval.py          Person A — search() over the Chroma index
build_catalog.py      raw Kaggle CSV -> data/products.parquet
build_index.py        parquet -> chroma/
run_index.sh          full rebuild (needs the raw CSV; see caveat below)
run_mcp.sh            start the MCP server on stdio
mcp_server/           Person B — MCP server
  server.py             tool registration, stdio entry point
  rag_tool.py           rag.search: adapter over retrieval.search
  web_tool.py           web.search: SerpApi, rate limit, allowlist
  providers.py          provider clients + fixture mode
  cache.py              TTL cache (one class, one instance per tool)
  jsonl_log.py          JSONL audit log with secret redaction
  allowlist.py          domain allowlist for live results
tests/                MCP server tests (pytest tests/test_mcp_server.py -q)
docs/DATA.md          corpus provenance and cleaning
docs/MCP.md           MCP tool schemas and safety notes
eval/                 20 hand-labelled retrieval queries
data/products.parquet 6,461 products (committed)
chroma/               vector index (gitignored — build locally)
logs/                 JSONL tool audit log (gitignored)
```

## Part B — Development and Modifications

What Person B built, and every change made to files owned by other lanes.

### What was built

One MCP server, `product-discovery`, exposing exactly two tools over **stdio**.
Full schemas and safety notes live in [`docs/MCP.md`](docs/MCP.md).

| Requirement | How it is met |
|---|---|
| Two working tools | `rag.search` (private Chroma catalogue) and `web.search` (live SerpApi) |
| Tool discovery | Standard `tools/list`; both tools verified in an MCP client and the Inspector |
| JSON schemas | Input **and** output schemas generated from Pydantic models, so they cannot drift from the code |
| Transport | stdio, launched via `run_mcp.sh` (works from any working directory) |
| TTL cache | `web.search` 180s (clamped to the required 60–300s window); `rag.search` 900s |
| Request log | Append-only JSONL at `logs/mcp_requests.jsonl` — request, response, timestamp, source URLs, cache hit, duration, error |
| Safety | Domain allowlist on live results, secret redaction, ToS/robots notes |

**`rag.search`** is a thin adapter over Person A's `search()` — retrieval is not
reimplemented, per the contract above. It returns `doc_id` as the citation
handle and preserves the hard-constraint and empty-result guarantees.

**`web.search`** returns `{title, url, snippet, price?, availability?}` and
degrades rather than crashing: a dead key, timeout or exhausted quota yields
`degraded: true` with an empty result list. This is deliberate — the same
process serves `rag.search`, so a third-party outage must not take down both.

**Caching** is one implementation (`mcp_server/cache.py`) instantiated once per
tool, because the two have different staleness semantics: live prices must
expire inside the graded window, while the Chroma index is static between
rebuilds. No new dependency was added for it.

**Tests:** `pytest tests/ -q` — 43 tests, no network, zero API quota spent.
Covers TTL expiry and clamping, secret redaction, the domain allowlist,
provider normalisation, degradation on a dead key, and the always-null
`rating`/`ingredients` contract.

### Fields the brief asks for that this corpus cannot supply

The brief specifies `rating` and `ingredients` on `rag.search`. Neither exists
in the dataset (see the corpus note above). They are **declared in the schema
and always emitted as `null`** — not omitted, so anyone diffing against the
brief can see they exist and see they are empty; and not fabricated, because an
invented rating would flow straight into a cited recommendation. Every response
carries `unavailable_fields: ["rating", "ingredients"]` so consumers can assert
this programmatically instead of parsing prose.

### Modifications to shared files

**`retrieval.py` (Person A's file)** — three changes, no behaviour change to the
search contract. A's smoke test still passes all seven cases unchanged.

1. The Chroma path was the relative string `"chroma"`, resolved against the
   caller's working directory. MCP clients launch the server from an arbitrary
   cwd, where this silently created an *empty* `chroma/` directory and then
   failed. It is now an absolute path derived from `__file__`, overridable with
   `CHROMA_PATH`.
2. The client and collection were opened at module import, so `import retrieval`
   raised if the index had not been built — which would have killed the whole
   MCP server at startup rather than failing one tool call. Initialisation is now
   lazy, inside `_collection()`.
3. `search()` called `_COL.count()` on every query and passed `n_results=0` when
   the collection was empty. It now short-circuits to `[]`.

**`requirements.txt`** — added `mcp==2.0.0`. This is the only new dependency;
`httpx`, `pydantic`, `tenacity` and `python-dotenv` were already pinned and are
reused rather than duplicated.

**`.gitignore`** — added `logs/` (the JSONL log contains full user query text).

**`README.md`** — added the API-key section at the top, the MCP server section,
this section, and filled in the previously empty *Repo layout* heading. Also
corrected the setup instructions: `./run_index.sh` cannot run on a fresh clone
because its first step needs the raw Kaggle CSV, which is gitignored;
`python build_index.py` is the working path since the parquet is committed.

### Post-integration fixes (after Part C landed)

**`rag.search` silently ignored every filter.** The tool exposed filters as flat
arguments (`max_price=30`) while the graph passed a nested dict
(`filters={"max_price": 30}`) — the shape the retrieval contract above documents.
The MCP SDK builds its argument model with Pydantic's default `extra="ignore"`
and emits no `additionalProperties: false`, so an unknown argument is dropped
with no error: every search ran unfiltered while looking completely healthy. The
only visible signal was `filters_applied: {}` in the response.

Fixed by accepting **both** shapes, flat winning on conflict, so the repo now
tells one story. Unrecognised keys inside `filters` are reported in a new
`warnings` field instead of being dropped. `docs/MCP.md` gained a worked example
— its absence was the real root cause, since the params table was correct but a
table is not what anyone reaches for when wiring up a call.

**The server stopped importing entirely.** Installing the LangGraph/OpenAI
dependency tree downgraded `mcp` from 2.0.0 to 1.29.0, which moved the server
class (`MCPServer` → `FastMCP`). `mcp_server/server.py` now imports either, and
`langchain`/`langgraph`/`openai` are declared in `requirements.txt` so the pin
cannot be broken silently again.

**The test suite gave a false green.** All 44 tests passed while the server could
not be imported at all, because nothing in the suite touched `server.py`. Added
registration tests that fail loudly on exactly that, plus regression tests for
both filter shapes and each of the four reported cases. Now 54.

**`.env` was tracked in git.** It had been renamed from `.env.example`, and
`.gitignore` does not apply to already-tracked files — the next real key
committed would have gone to GitHub. `.env.example` restored, `.env` untracked.

## Part C — LangGraph Orchestration

Four-node graph: Router → Planner → Retriever → Critic. Full pipeline tested
against 10 hand-written transcripts covering age-stripping, price ranges,
brand/subcategory filters, live-intent triggers, safety flags, and the
known out-of-scope case (a non-toy query against a toy catalog).

### Nodes

| Node | Job | LLM used? |
|---|---|---|
| Router | Extracts `max_price`, `min_price`, `subcategory`, `brand`, `safety_flags`, `age_mentioned`, `raw_task` from the transcript | Yes — structured JSON output |
| Planner | Decides whether to call `web.search` in addition to `rag.search`, based on live-intent trigger words | No — rule-based, deterministic |
| Retriever | Calls both MCP tools, reconciles `rag.search`/`web.search` results by title similarity (RapidFuzz), computes discrepancy flags | No |
| Critic | Synthesizes a short, cited, grounded answer from reconciled evidence | Yes — structured JSON output |

### Router

- Age is extracted for safety-flag purposes only, never used as a filter —
  per the corpus note above, age filtering degrades retrieval quality here.
- `subcategory` is constrained to the actual set of values present in
  `products.parquet`; the model cannot invent a category.
- Out-of-scope requests (e.g., non-toy items) still extract real
  price/brand constraints — only `subcategory` is nulled.
- Output is validated against a strict schema (type + allowed-value checks)
  before use. On failure, the node retries once with the validation error
  fed back to the model; if it fails twice, falls back to an unfiltered,
  all-null constraint set rather than passing bad data downstream.

### Planner

Rule-based by design (see `docs/MCP.md`'s "For Person C" section) — always
calls `rag.search`; adds `web.search` when the transcript matches a
live-intent trigger list (current/price/availability/now/latest, plus
availability- and existence-phrasing). Logs which specific triggers matched
in `plan.reason`, for transparency in the agent step log.

### Retriever

- Parses raw MCP `TextContent` responses into plain dicts.
- Reconciles `rag.search` and `web.search` results by title similarity
  (RapidFuzz `token_set_ratio`, threshold 75, after stripping retailer/mock
  boilerplate from titles) — never by `sku`, per the corpus note.
- Classifies each result as `matched`, `rag_only`, or `web_only`.
- Flags discrepancies per matched pair: price mismatch (>$5 or >15%), a
  live rating present where the catalog has none, and whether the live
  data came back `degraded`/mock (`MOCK_WEB_SEARCH=1`).

### Critic

- Computes catalog relevance in code (rag similarity `score` ≥ 0.5) before
  the LLM ever runs — the model is told the fact ("no relevant results"),
  it doesn't judge the threshold itself.
- `rating` and `ingredients` are structurally excluded from what the model
  sees, not just null-checked, so they can't be referenced by mistake.
- Mock/degraded live data is explicitly hedged as unconfirmed rather than
  stated as fact.
- Non-empty `safety_flags` produce a brief natural-language caution in the
  spoken answer.
- Same validate → retry-once → fail-closed pattern as the Router.

### Integration point

`entrypoint.py` exposes one async function, `get_recommendation(transcript: str) -> dict`,
plus `shutdown()`. This is the only thing Person D's UI needs to call — see
`docs/` or ask Person C for the exact output shape.

### Known limitations

- MCP server's `filters_applied` does not currently reflect/enforce
  `brand`/`subcategory` filters server-side (flagged to Person B) — retrieval
  precision on brand-scoped queries is lower than intended until fixed.
- Fuzzy-match threshold (80) was tuned against `MOCK_WEB_SEARCH=1` fixture
  data, which has different title formatting than real SerpApi results —
  worth re-validating once tested against a real key.
- Graph doesn't support any follow-up/correction turns 
