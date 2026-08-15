# Prompts — Person C (LangGraph Orchestration)

This folder documents every prompt and decision rule used by the
orchestration graph, per the Prompt Disclosure grading requirement. Each
file below corresponds to one node in the graph.

| File | Node | LLM? | What it does |
|---|---|---|---|
| `agent_prompt.py` — `agentRole` | Routing | Yes | Extracts structured shopping constraints (price range, subcategory, brand, safety flags, age handling) from the raw voice transcript |
| `planner_rubric.md` | Planning | No | Documents the rule-based logic for deciding whether to also call `web.search` |
| `agent_prompt.py` — `criticRole` | Critic | Yes | Synthesizes a short, cited, grounded recommendation from reconciled catalog + live evidence |

## Shared design pattern: validate → retry once → fail closed

Both LLM-backed nodes (Router, Critic) follow the same reliability pattern,
implemented in `validate_parse.py`:

1. Call the LLM, expecting a strict JSON object matching a defined schema.
2. Validate the response: is it parseable JSON, are all required fields
   present with the correct type, and do values pass semantic checks
   (e.g., `subcategory` must be one of the catalog's real subcategories;
   `min_price` cannot exceed `max_price`)?
3. If validation fails, retry once — the model's own invalid output plus
   the specific validation error are fed back, asking it to correct just
   that issue.
4. If validation still fails after the retry, fail closed: fall back to a
   safe default (an unfiltered constraint set for the Router; a plain
   "couldn't produce a reliable answer" message for the Critic) rather than
   passing unvalidated or partially-broken data further into the pipeline.

This choice was made deliberately so that a single malformed model response
can never silently corrupt downstream state or produce an ungrounded claim
— every failure mode either self-corrects or degrades safely and visibly.

## Router — key design notes

- Age is extracted only to populate `safety_flags`; it is never used to
  filter results, since age-qualified queries are a documented weak point
  of this corpus's retrieval quality (`docs/DATA.md`).
- `subcategory` must be one of the actual values present in the indexed
  catalog (`products.parquet`) — the model cannot invent a category that
  doesn't exist.
- `safety_flags` is drawn from a small fixed vocabulary
  (`small_parts_choking_hazard`, `age_inappropriate`, `allergen_material`,
  `battery_hazard`, `sharp_edges_or_points`, `strangulation_hazard`) rather
  than free text, so downstream code can check for specific flags reliably.
- Out-of-scope requests (not a toy/game at all) still have their real
  price/brand constraints extracted normally — only `subcategory` is
  nulled, so a stated budget isn't discarded just because the category
  doesn't apply.

## Critic — key design notes

- Catalog relevance is computed in code before the LLM runs
  (`has_relevant_results`, based on the rag item's similarity `score`,
  threshold 0.5) — the model is told the fact, it does not judge the
  threshold itself. This keeps a numeric decision deterministic and
  testable rather than left to model judgment.
- `rating` and `ingredients` are structurally excluded from what the model
  is shown (not just null-checked), since this corpus never has real
  values for either field — the model cannot reference what it never sees.
- Live web data flagged as mock/degraded (`MOCK_WEB_SEARCH=1` or a dead
  SerpApi key) is explicitly hedged as unconfirmed in the answer, never
  stated as verified fact.
- Price discrepancies between catalog and live listings are surfaced, not
  silently resolved by picking one source.
- Non-empty `safety_flags` produce a brief, natural caution in the spoken
  answer; an empty list produces no caution (tested explicitly, so the
  model doesn't over-trigger cautions on unrelated queries).

## Testing

Both prompts were iteratively developed and validated against 10 hand-written
test transcripts covering: age-stripping, empty constraints, live-intent
triggers (and a deliberate false-positive case), brand/price filtering,
price ranges, a rating request (to confirm no fabrication), an out-of-scope
non-toy query, a safety-flag case, and a known-hard retrieval case flagged
in `docs/DATA.md`. See `tests/test_all_nodes.py`.
