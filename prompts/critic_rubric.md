# Critic Rubric

**Used by:** `critic_node` in `orchestration.py`

**Node:** Critic (also referred to as Answerer/Critic per the project brief)

**LLM used:** Yes — structured JSON output, same model as the Router.

## Purpose

The Critic is the last node in the graph. It receives reconciled evidence
from the Retriever (matched/rag_only/web_only catalog and live items, with
discrepancy flags already computed) and produces the final spoken and
on-screen answer. Its core responsibility is enforcing grounding: every
claim in the answer must trace back to a specific citable item, and nothing
the corpus cannot support (rating, ingredients, unverified live data) may be
presented as fact.

## Inputs (the "evidence" object)

The Critic never sees raw `merged_results` or full state — it receives a
minimal, pre-filtered object built by `build_grounding_context()`:

```json
{
  "raw_task": string,
  "has_relevant_results": bool,
  "safety_flags": [string],
  "grounding_context": [
    {
      "match_type": "matched" | "rag_only" | "web_only",
      "title": string,
      "catalog_price": float | null,
      "live_price": string | null,
      "live_availability": string | null,
      "discrepancy_notes": [string],
      "citation": {"doc_id": string | null, "url": string | null, "claim": string}
    }
  ]
}
```

Two fields are computed in code, not judged by the model:

- **`has_relevant_results`** — `True` only if at least one rag item's
  similarity `score` clears a threshold (0.5). Vector search always returns
  its top-k nearest neighbors even when nothing is a good match (see the
  "eco-friendly stainless steel cleaner" test case, which returns paint and
  primer products at ~0.45–0.47 similarity) — the model is told the
  resulting fact rather than asked to eyeball a raw score itself.
- **`grounding_context`** — pre-filtered to exclude low-relevance items when
  `has_relevant_results` is false, and structurally omits `rating` and
  `ingredients` entirely (not merely null-checked) since this corpus never
  has real values for either field. The model cannot reference a field it
  is never shown.

## Rules

1. **No relevant results → say so plainly.** If `has_relevant_results` is
   `false`, state clearly that nothing in the catalog matches — do not force
   a recommendation just because some item happens to be present in the
   evidence.
2. **Every specific product claim must be grounded.** Name, price, and
   availability claims must come from an item in `grounding_context` and be
   attributable to that item's `citation`. No claim may be invented.
3. **Never state or imply a rating or ingredient list.** These fields are
   deliberately absent from the evidence; their absence should be treated
   as "does not exist," not "wasn't mentioned."
4. **Price mismatches are surfaced, not resolved.** If `discrepancy_notes`
   contains `price_mismatch`, both the catalog and live price are stated —
   the model does not silently pick one.
5. **Mock/degraded live data is hedged, not presented as fact.** If
   `discrepancy_notes` contains `web_data_is_mock_or_degraded`, live
   price/availability is described as unconfirmed rather than verified.
6. **Safety flags produce a brief caution.** If `safety_flags` is
   non-empty, `spoken_answer` includes a short, plainly-worded caution
   reflecting the flag(s). If `safety_flags` is empty, no caution is added
   — tested explicitly so the model doesn't over-trigger on unrelated
   queries (see `tests/test_all_nodes.py`).
7. **Citations reflect only what was actually said.** `citations` must
   correspond to items referenced in `spoken_answer`/`full_answer`, not the
   full evidence list handed to the model. (Identified as a bug during
   testing — an early version cited every item in the evidence regardless
   of whether it appeared in the answer.)
8. **Spoken answer stays short.** `spoken_answer` targets 2–3 sentences,
   roughly a 15-second TTS read, matching the project brief's spoken-summary
   requirement. `full_answer` carries the fuller detail for on-screen
   display.
9. **Output is strict JSON, nothing else** — `{spoken_answer, full_answer, citations}`.

## Reliability pattern

Same validate → retry-once → fail-closed approach as the Router (see
`prompts/README.md`). On two consecutive validation failures, the node
returns a generic "wasn't able to put together a reliable answer" message
with empty citations, rather than surfacing malformed or partially-grounded
output to the user.

## Known limitation

The relevance threshold (0.5) and the fuzzy-match threshold used upstream
in the Retriever were both tuned against a small number of hand-tested
queries. They are reasonable starting points, not empirically optimized
values — a larger eval set (beyond the project's 20 hand-labeled retrieval
queries) would allow tighter tuning of both.
