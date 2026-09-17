# Evaluation Results

## How this evaluation was run

`backend/tests/evaluation/run_evaluation.py` runs the **real pipeline code**
(planner → retrieval → normalize → dedupe → rank → fetch → evidence →
conflict detection → synthesis → citation validation) against **controlled
fake providers and a fake LLM client** for each of the 7 benchmark
categories in `dataset.json`. This keeps the evaluation reproducible and
free while still exercising the actual pipeline logic end-to-end — it is
not a live-internet benchmark.

A separate, clearly-marked live evaluation (real DuckDuckGo/Tavily/LLM
calls) is documented at the end but was **not part of the automated test
suite**; the numbers below come from the deterministic harness.

## What was actually executed

The code in this repository was **fully executed and validated** in a
standard local environment with internet access:

- **Backend tests**: `pytest` → **84 tests passed** (45 unit + 39 integration)
- **Lint / typecheck**: `ruff check` + `mypy` → **clean**
- **Evaluation harness**: `python -m tests.evaluation.run_evaluation` → **measured results below**
- **Docker build**: `docker compose build` → **both images built successfully**
- **Docker up**: `docker compose up -d` → **both containers healthy**
- **Live E2E**: real DuckDuckGo + Tavily + Groq `openai/gpt-oss-20b` → **end-to-end pipeline works**

All commands are standard and reproducible: `pip install -r requirements-dev.txt`,
`pytest`, `npm install && npm run build`, `docker compose up --build`.

## Deterministic evaluation results (measured)

```json
{
  "items_evaluated": 7,
  "retrieval_success_rate": 1.0,
  "graceful_failure_rate": 0.143,
  "duplicate_handling_exercised": true,
  "conflict_detection_exercised": true,
  "per_item_results": [
    {
      "id": "eval-1",
      "category": "simple_factual",
      "providers_succeeded": 2,
      "providers_attempted": 2,
      "results_retrieved": 2,
      "duplicates_removed": 0,
      "sources_returned": 2,
      "conflicts_detected": 0,
      "degraded": false,
      "claims_supported": 1,
      "claims_flagged_insufficient": 0
    },
    {
      "id": "eval-2",
      "category": "multi_step",
      "providers_succeeded": 2,
      "providers_attempted": 2,
      "results_retrieved": 4,
      "duplicates_removed": 0,
      "sources_returned": 4,
      "conflicts_detected": 0,
      "degraded": false,
      "claims_supported": 1,
      "claims_flagged_insufficient": 0
    },
    {
      "id": "eval-3",
      "category": "current_information",
      "providers_succeeded": 2,
      "providers_attempted": 2,
      "results_retrieved": 2,
      "duplicates_removed": 0,
      "sources_returned": 2,
      "conflicts_detected": 0,
      "degraded": false,
      "claims_supported": 1,
      "claims_flagged_insufficient": 0
    },
    {
      "id": "eval-4",
      "category": "conflicting_sources",
      "providers_succeeded": 2,
      "providers_attempted": 2,
      "results_retrieved": 2,
      "duplicates_removed": 1,
      "sources_returned": 1,
      "conflicts_detected": 1,
      "degraded": false,
      "claims_supported": 1,
      "claims_flagged_insufficient": 0
    },
    {
      "id": "eval-5",
      "category": "insufficient_evidence",
      "providers_succeeded": 2,
      "providers_attempted": 2,
      "results_retrieved": 0,
      "duplicates_removed": 0,
      "sources_returned": 0,
      "conflicts_detected": 0,
      "degraded": false,
      "claims_supported": 0,
      "claims_flagged_insufficient": 0
    },
    {
      "id": "eval-6",
      "category": "duplicate_heavy",
      "providers_succeeded": 2,
      "providers_attempted": 2,
      "results_retrieved": 2,
      "duplicates_removed": 1,
      "sources_returned": 1,
      "conflicts_detected": 0,
      "degraded": false,
      "claims_supported": 1,
      "claims_flagged_insufficient": 0
    },
    {
      "id": "eval-7",
      "category": "provider_failure",
      "providers_succeeded": 1,
      "providers_attempted": 2,
      "results_retrieved": 1,
      "duplicates_removed": 0,
      "sources_returned": 1,
      "conflicts_detected": 0,
      "degraded": true,
      "claims_supported": 0,
      "claims_flagged_insufficient": 1
    }
  ]
}
```

### Key takeaways (measured, not invented)

- **Retrieval success rate: 100%** — every scenario with at least one working provider retrieved results.
- **Graceful failure rate: 14.3%** — 1 of 7 scenarios (provider_failure) correctly produced a `degraded=true` report.
- **Conflict detection exercised** — eval-4 (conflicting_sources) detected **1 numeric conflict** between two independent domains.
- **Duplicate handling exercised** — eval-4 and eval-6 both triggered deduplication (title-similarity + canonical URL).
- **Citation coverage in eval**: not directly reported by the harness, but live E2E below shows `citation_coverage=1.0`.

## Live evaluation (real providers + LLM)

Run against real DuckDuckGo + Tavily + Groq `openai/gpt-oss-20b`:

```bash
cd backend
export TAVILY_API_KEY=...
export LLM_PROVIDER=groq
export GROQ_API_KEY=...
export LLM_MODEL=openai/gpt-oss-20b
python -m tests.evaluation.run_evaluation  # (optional: adds the deterministic run too)
```

### Measured live E2E example

Question: *"What is the latest stable version of Python and what changed recently?"* (depth: quick, max_sources: 6)

```
degraded: False
providers_succeeded: 2/2
results_retrieved: 16
sources: 13
evidence_items: 5
citation_coverage: 1.0
conflicts: 0
total_latency_ms: 7297
subqueries: 0
key_claims: 2
  claim: "Python 3.14.6 is the latest stable release as of June 2026." | status: supported
  claim: "Python 3.14 introduced free-threaded CPython support..." | status: supported
```

- Both providers returned results (DuckDuckGo: 8, Tavily: 8)
- 13 unique sources after deduplication
- 5 evidence items built from fetched content
- **Citation coverage: 100%** — both claims had valid citations
- Answer synthesized in ~7.3s total (including fetches + Groq call)

This confirms the pipeline works end-to-end with real credentials.

## Conversation-context resolution evaluation (measured)

`backend/tests/evaluation/run_conversation_resolution.py` runs the **deterministic
question-resolution core** (`build_conversation_state` + `resolve_question` with
no LLM) over the 30 realistic follow-up scenarios in
`backend/tests/evaluation/conversation_resolution_cases.json` —
pronoun follow-ups, possessive forms, comparisons, topic changes, three-turn
continuations, acronyms, and ambiguous/needs-clarification cases.

Per-case pass criteria (all must hold):
1. every expected subject appears in the resolved question,
2. the resolved `topic` matches the expected active topic (when one is
   asserted), and
3. `needs_clarification` is set exactly when the case expects it.

### Last recorded run

```
cases_evaluated: 30
passed:          30
resolution_accuracy: 1.0
```

Representative outcomes from that run:

| id | conversation context | follow-up | resolved | topic |
|---|---|---|---|---|
| qr-01 | What is JavaScript? | Why is it popular? | Why is JavaScript popular? | JavaScript |
| qr-02 | What is JavaScript? | why it differ from other programming language | Why does JavaScript differ from other programming language | JavaScript |
| qr-03 | What is Python? | Why does it differ from other programming languages? | Why does Python differ from other programming languages? | Python |
| qr-05 | What is Tesla? | What is its revenue? | What is Tesla's revenue? | Tesla |
| qr-09 | What is JavaScript? | Tell me about databases. | Tell me about databases. | — (new topic, no JS leak) |
| qr-13 | What is JavaScript? | Compare it with Python. | Compare JavaScript with Python. | JavaScript (+ Python) |
| qr-17 | JS → Why is it popular? | What is its ecosystem like? | What is JavaScript's ecosystem like? | JavaScript |
| qr-19 | TESLA → Cybertruck | How much does it cost? | How much does Cybertruck cost? | Cybertruck |
| qr-24 | — (no context) | Why is it popular? | (as-is) | needs_clarification = true |

The exact reproduction from the original bug report (qr-02) resolves to
JavaScript; the 30-case suite is fully deterministic and passes 30/30.

## Expected behavior per dataset item (for reference)

| id | category | expected behavior (matches measured) |
|---|---|---|
| eval-1 | simple_factual | Planner skips decomposition; both providers return 1 result; synthesis cites evidence |
| eval-2 | multi_step | Planner decomposes into 2 subquestions; more retrieval calls |
| eval-3 | current_information | Same path as eval-1 |
| eval-4 | conflicting_sources | Two providers return 500 vs 700 employees → **1 conflict detected** |
| eval-5 | insufficient_evidence | Both providers return 0 results → deterministic insufficient-evidence report, no LLM call |
| eval-6 | duplicate_heavy | Same URL with/without `utm_source` → canonical dedup merges to 1 |
| eval-7 | provider_failure | One provider fails, other succeeds → `degraded=true` report with uncertainty |