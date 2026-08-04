# Voice-to-Voice Product Discovery Assistant

Agentic voice assistant for product discovery: speak a request, a LangGraph
pipeline routes it, retrieves grounded evidence from a private catalog and
optionally the live web via MCP, and answers by TTS with on-screen citations.

## Lanes

| Person | Owns | Status |
|---|---|---|
| A | Data + retrieval (`retrieval.py`, Chroma index) | Done — working against real data |
| B | MCP server (`web.search`, `rag.search`) | |
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

## Repo layout

## Workflow

Commit directly to `main` — with four lanes touching different files over ten
days, PR review costs more than it saves. `git pull` before you start,
`git push` when you stop.