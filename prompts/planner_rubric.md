# Planner Rubric

**Used by:** `planner_node` in `orchestration.py`
**Node:** Planning
**LLM used:** No — this node is rule-based and deterministic, by design.

## Why rule-based, not an LLM call

The Planner's only decision is: in addition to always calling `rag.search`,
should we also call `web.search`? This is a narrow, binary decision with a
small, enumerable set of signals (does the transcript indicate the user wants
live price/availability information). Given how deterministic this logic is,
an LLM call here would add latency and non-determinism without improving
accuracy, and would make the decision harder to test exhaustively. A
rule-based check can be unit-tested against every transcript with 100%
reproducibility, which an LLM-based decision cannot guarantee run-to-run.

This mirrors the source project's own guidance (`docs/MCP.md`, "For Person C"
section): *"prefer rag.search for product facts; also call web.search when
the user says current price, availability, now, or latest."*

## The rule

1. **Always call `rag.search`.** The private catalog is the grounded source
   of truth for every query, including out-of-scope ones (an empty/low-score
   result set is itself useful, cited information — see Critic rubric).

2. **Call `web.search`** if the raw transcript (not the Router's cleaned
   `raw_task`, deliberately — see note below) contains any of the following
   trigger phrases, case-insensitive substring match:

   ```
   Time/currency:  current, currently, now, right now, latest, today
   Price:          price, cost, how much, going for, still, changed
   Availability:   available, availability, in stock, out of stock,
                   sold out, can i buy, can i get, still selling
   Existence:      still exist, discontinued, still sold, anymore
   ```

3. **Log which specific trigger(s) matched** in `plan.reason`, so the
   decision is transparent and auditable in the agent step log — not just a
   bare true/false.

## Why the raw transcript, not `raw_task`

`raw_task` (from the Router) is explicitly a cleaned/stripped restatement of
the user's request — price, brand, and age details are intentionally removed
from it. Trigger words like "still" or "now" could easily be dropped during
that cleaning step, so the Planner checks the original transcript to avoid
losing a live-intent signal that never should have been stripped in the
first place.

## Known limitation

Keyword matching produces occasional false positives — e.g., "a toy that
will still work outdoors in the rain" triggers on "still" even though the
query is about durability, not live pricing. This was identified during
testing and accepted as a reasonable tradeoff: the cost of a false positive
is one extra `web.search` call, not an incorrect answer. A false negative
(missing genuine live intent) would be the more costly failure mode, so the
trigger list errs toward recall over precision.
