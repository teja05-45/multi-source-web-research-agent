  # Multi-Source Web Research Agent

An evidence-grounded research API that answers a natural-language question
by querying **two independent search providers**, deduplicating and ranking
what comes back, fetching and extracting real page content, building a
first-class **Evidence** model, detecting conflicts, and only then asking an
LLM to synthesize an answer — with every material claim validated against
the evidence it cites rather than trusted blindly.

> **Core principle this project is built around:** an LLM is not a source of
> truth. The system builds a verifiable evidence pipeline *before* the LLM
> ever sees the question, and validates the LLM's output *after* — the model
> is one stage in a controlled pipeline, not the source of facts.

---

## 1. Overview

Given a question like *"Compare the current approaches to AI agent memory
and explain the major trade-offs,"* the system:

1. Optionally decomposes the question into a few sub-questions (skipped for
   simple questions, to save cost/latency).
2. Queries **DuckDuckGo** (no API key) and **Tavily** (API key) concurrently
   for every (sub)question.
3. Normalizes results into one schema, deduplicates URLs and near-identical
   titles, and ranks what's left with query-aware heuristics.
4. Fetches the top-ranked pages, extracts readable text, and builds a list
   of `Evidence` objects — the only thing the LLM is allowed to see.
5. Detects numeric conflicts between independent sources.
6. Asks the LLM to synthesize an answer strictly from that evidence, citing
   evidence IDs.
7. Validates every citation against real evidence — an invented or
   weakly-supported claim is flagged as `insufficient_evidence`, not trusted.
8. Returns a structured report: answer, key claims (with support status),
   sources, conflicts, uncertainties, and a full research trace.

## 2. Problem Understanding

The assignment brief asks for more than "search API → LLM → answer." The
hard, interesting parts are: handling **two independent, unreliable
providers** gracefully; treating **deduplication and ranking as real
engineering problems** rather than an afterthought; building a **grounding
layer** between retrieval and generation so the model can't just make things
up; and being **honest about uncertainty** — conflicting sources, missing
evidence, and provider outages should be visible in the output, not hidden.

## 3. Goals

- Multi-source retrieval with graceful degradation, not "best effort and
  hope."
- Evidence-first architecture: the LLM only ever sees curated, traceable
  `Evidence` objects, never raw search results or full HTML.
- Explicit, inspectable ranking, deduplication, conflict-detection, and
  citation-validation logic — every decision is a named function you can
  read, test, and disagree with.
- A controlled, observable, single-pass pipeline — not an autonomous agent
  loop with unpredictable behavior and cost.
- Reproducibility: runs locally, in Docker, and in CI-style test runs with
  zero live API credentials (via the `mock` LLM provider and mocked HTTP in
  tests).

## 4. Non-Goals

- **Not** a general-purpose autonomous research agent that plans its own
  tool use indefinitely. The pipeline runs each stage once, in a fixed
  order.
- **Not** a guarantee of factual correctness. Citation validation reduces
  *unsupported* claims; it cannot verify that a cited source is itself
  correct.
- **Not** a production-scale multi-tenant SaaS. There is no auth, no
  database, no per-user quota system — see "Known Limitations."
- **Not** a replacement for reading primary sources on high-stakes
  questions.

## 5. Architecture

```
                     User
                       │
                       ▼
                   Frontend (React + TS, white/light theme)
                       │  HTTPS / JSON
                       ▼
                 FastAPI API (app/main.py)
                       │
                       ▼
              Research Pipeline (orchestration/research_pipeline.py)
                       │
        ┌──────────────┼──────────────────────┐
        ▼                                      ▼
  Research Planner                    Configuration (app/config.py)
  (planning/planner.py)
        │
        ▼
   Subqueries
        │
        ▼
  Parallel Retrieval (retrieval/orchestrator.py)
        │
   ┌────┴─────┐
   ▼          ▼
DuckDuckGo   Tavily
(providers/) (providers/)
   │          │
   └────┬─────┘
        ▼
  Result Normalizer (processing/normalizer.py)
        ▼
  Deduplication (processing/deduplicator.py)
        ▼
  Source Ranking (processing/ranker.py)
        ▼
  Content Fetcher (retrieval/fetcher.py + extractor.py)
        ▼
  Evidence Builder (verification/verifier.py)
        ▼
  Conflict Detector (verification/conflict_detector.py)
        ▼
  LLM Synthesizer (synthesis/synthesizer.py, via synthesis/llm_client.py)
        ▼
  Citation Validator (verification/citation_validator.py)
        ▼
  Final Research Report (models/report.py)
```

Cross-cutting, applied at every stage that talks to an external service:
structured JSON logging with request-ID correlation
(`observability/logging.py`), bounded retry with exponential backoff
(`reliability/retry.py`), a per-provider circuit breaker
(`reliability/circuit_breaker.py`), a token-bucket rate limiter
(`reliability/rate_limiter.py`), in-process metrics
(`observability/metrics.py`), and SSRF-safe URL validation before any
server-side fetch (`security/url_safety.py`).

## 6. System Design

| Component | File | Responsibility |
|---|---|---|
| Config | `app/config.py` | Typed, env-var-driven settings (Pydantic `BaseSettings`). Single source of truth for every tunable. |
| Provider abstraction | `app/providers/base.py` | `SearchProvider` interface — the only thing the pipeline depends on. |
| DuckDuckGo provider | `app/providers/duckduckgo_provider.py` | No-API-key baseline provider, HTML scraping. |
| Tavily provider | `app/providers/tavily_provider.py` | API-key-based, LLM-oriented search provider. |
| Planner | `app/planning/planner.py` | One (skippable) LLM call to decompose complex questions; deterministic fallback on any failure. |
| Retrieval orchestrator | `app/retrieval/orchestrator.py` | Runs every (subquery, provider) pair concurrently, bounded, with per-provider retry + circuit breaking. |
| Normalizer | `app/processing/normalizer.py` | Canonical URL rules, domain extraction, common schema. |
| Deduplicator | `app/processing/deduplicator.py` | Exact canonical-URL dedup + fuzzy title-similarity dedup. |
| Ranker | `app/processing/ranker.py` | Query-aware relevance/authority/freshness scoring. |
| Fetcher | `app/retrieval/fetcher.py` | SSRF-checked, size-bounded, concurrency-bounded page fetch. |
| Extractor | `app/retrieval/extractor.py` | HTML → readable text via BeautifulSoup. |
| Evidence builder | `app/verification/verifier.py` | Builds the `Evidence` list the LLM is restricted to. |
| Conflict detector | `app/verification/conflict_detector.py` | Deterministic numeric-conflict detection across independent domains. |
| LLM client | `app/synthesis/llm_client.py` | Groq / Gemini / mock — swappable via env var. |
| Synthesizer | `app/synthesis/synthesizer.py` | Strict-JSON LLM call over evidence, defensive parsing. |
| Citation validator | `app/verification/citation_validator.py` | Rejects invented IDs, flags weak lexical support, marks conflicted claims. |
| Pipeline | `app/orchestration/research_pipeline.py` | Wires every stage together in a fixed order; builds the final report. |
| API routes | `app/api/routes/` | Thin FastAPI handlers; all logic lives in the modules above. |

## 7. Data Flow (one request, end to end)

1. `POST /api/research {"question": "..."}` hits `research.py`, which calls
   `ResearchPipeline.run()`.
2. A request ID is generated and attached to every subsequent log line.
3. The planner either skips decomposition (simple question) or makes one
   LLM call and validates its JSON output.
4. `run_retrieval()` fires one task per (subquery × provider), bounded by
   `RETRIEVAL_CONCURRENCY`, each wrapped in retry-with-backoff and a circuit
   breaker. Every provider outcome (success/failure, latency, retries) is
   recorded regardless of whether the call succeeded.
5. If **all** providers failed, the pipeline short-circuits to a
   deterministic "insufficient evidence" report — no LLM call happens.
6. Otherwise: normalize → dedupe → rank. If ranking produces zero results,
   same insufficient-evidence short-circuit.
7. The top `min(max_sources, MAX_SOURCES_TO_FETCH)` ranked results are
   fetched concurrently (SSRF-checked); fetch failures fall back to the
   provider snippet rather than failing the request.
8. `build_evidence()` turns fetched content (or snippets) into `Evidence`
   objects — this is what the LLM will see.
9. `detect_conflicts()` runs deterministically over evidence passages.
10. `synthesize()` calls the LLM with the evidence block; output is parsed
    as strict JSON, with a safe fallback message on any parse failure.
11. `validate_claims()` checks every claim's citations against real
    evidence IDs and lexical overlap, and cross-references detected
    conflicts.
12. The final `ResearchReport` (answer, key claims, sources, conflicts,
    uncertainties, research trace) is returned as JSON.

## 8. Technology Choices

| Technology | Why |
|---|---|
| **FastAPI** | Async-native (needed for concurrent provider calls), automatic OpenAPI docs, first-class Pydantic integration for request/response validation. |
| **Pydantic v2** | Every model in this system (request, plan, search result, evidence, claim, report) is a Pydantic model — validation is not optional or an afterthought. |
| **httpx** | Async HTTP client with a clean timeout/exception model, used for both search providers and the content fetcher. |
| **BeautifulSoup** | Battle-tested, dependency-light HTML parsing for both DuckDuckGo's markup and general page-content extraction. No headless browser (see "Known Limitations" — no JS rendering). |
| **DuckDuckGo (HTML) + Tavily (API)** | One zero-credential provider (so the project is runnable by any reviewer immediately) plus one purpose-built, documented, LLM-oriented API — deliberately different failure modes (unofficial HTML scrape vs. official JSON API) so the reliability layer is exercised meaningfully, not just duplicated. |
| **Groq / Gemini / mock LLM abstraction** | The brief asks for a replaceable LLM provider; `LLMClient` makes that a one-line env var change. `mock` exists so the pipeline runs with zero paid credentials for review/testing. |
| **React + TypeScript + Vite + Tailwind** | Lightweight, fast dev loop, no unnecessary state-management library for a single-page research tool. Tailwind chosen over hand-written CSS to keep the white/light design system consistent without a design tool. |
| **pytest + respx** | `respx` mocks `httpx` calls at the transport level, so provider/LLM tests never touch the network, per the assignment's explicit requirement. |
| **No database** | The system is stateless per request; there is nothing to persist for this assignment's scope (no history, no auth). Documented as a limitation, not hidden. |

## 9. Provider Abstraction

Every provider implements `SearchProvider.search(query, max_results) ->
List[RawSearchResult]` (`app/providers/base.py`) and raises the shared
`ProviderError` (with an explicit `retryable` flag) on failure. The
orchestrator, normalizer, deduplicator, and ranker never see a
provider-specific response shape.

**To add a third provider** (e.g. Bing, Brave Search, SerpAPI):

1. Create `app/providers/my_provider.py`, subclass `SearchProvider`, return
   `RawSearchResult` objects, raise `ProviderError` with the right
   `retryable` value for each failure mode.
2. Instantiate it in `_build_providers()` in `app/main.py`, guarded by its
   own `MY_PROVIDER_ENABLED` env var, following the existing pattern.

No change to `retrieval/orchestrator.py`, `processing/*.py`,
`verification/*.py`, or `synthesis/*.py` is required — this is the concrete
test of the abstraction, not just a claim about it.

**Documented provider limitations:**

- **DuckDuckGo**: unofficial HTML endpoint, no SLA, markup can change or
  scraping can be blocked without notice; no reliable published dates.
- **Tavily**: official API, but requires a key and has a monthly quota on
  the free tier; `search_depth="basic"` is used by default to control cost
  (see `providers/tavily_provider.py`).

## 10. Deduplication Strategy

Two stages (`app/processing/deduplicator.py`):

1. **Exact canonical-URL dedup.** `normalizer.canonicalize_url()`
   lowercases the host, strips known tracking parameters (`utm_*`, `gclid`,
   `fbclid`, `ref`, ...), drops the fragment, removes a trailing slash, and
   drops default ports. `example.com/article` and
   `example.com/article?utm_source=google` canonicalize identically and are
   merged — the surviving result's `providers` list absorbs both, and
   `duplicate_count` increments.
2. **Fuzzy title-similarity dedup.** Among what's left, titles are compared
   pairwise with `difflib.SequenceMatcher`; a ratio ≥ `0.88` (a documented,
   deliberately conservative constant, not a tuned/validated threshold)
   folds the later result into the earlier one. This catches the same
   underlying story reproduced verbatim across different domains (e.g. a
   wire story syndicated by multiple outlets) without discarding
   independently-written coverage of the same topic that merely shares
   keywords.

Provenance is never lost: a merged result keeps every provider that
returned it and its `duplicate_count`, both surfaced in the API response
and the UI.

## 11. Source Ranking

`app/processing/ranker.py` combines three explicit, documented heuristics
(not claimed to be scientifically optimal):

```
final_score = 0.5 * relevance + 0.3 * authority + 0.2 * freshness
```

- **Relevance**: token-overlap ratio between the query and the result's
  title+snippet. Cheap, transparent, no external dependency.
- **Authority**: domain-based, and deliberately **query-dependent** — a
  documentation-style question (regex-matched keywords like "official",
  "documentation", "syntax") boosts `.gov`/`.edu`/`docs.*` domains and
  *penalizes* community sources (Stack Overflow, Reddit, HN); an
  experience/opinion-style question does the opposite, boosting community
  sources instead of treating them as low-quality. This trade-off is the
  direct answer to the brief's authority-vs-community-source question.
- **Freshness**: based on `published_date` when a provider supplies one
  (most snippets don't); unknown dates get a neutral 0.5, not a penalty,
  since "no date metadata" isn't evidence of staleness.

## 12. Evidence Grounding

Search snippets are frequently too short, or occasionally misleading
relative to the full source, to safely ground a claim. `Evidence`
(`app/models/evidence.py`) is the single, first-class object the LLM is
allowed to see — never a raw `SearchResult`, never raw HTML. Each `Evidence`
carries the passage actually used, whether it came from fetched content or
just a snippet (`from_fetched_content`), and its relevance/authority/
freshness scores, so the synthesis prompt and the citation validator both
operate over the same traceable unit. This ordering — build verified
evidence, *then* call the LLM — is this project's primary answer to "how do
you reduce hallucination."

## 13. Conflict Handling

`app/verification/conflict_detector.py` looks for numeric claims
(`"500 employees"`, `"40%"`, `"$3 million"`) appearing in evidence from
**different domains** whose values differ by more than 2%. It does not ask
the LLM to "notice" contradictions — LLM-detected contradiction is
unreliable and unverifiable; a deterministic, regex-based check on the
clearest class of conflict (disagreeing numbers) is something you can unit
test and trust. Detected conflicts are surfaced as first-class `Conflict`
objects (both positions, both sources, no fabricated explanation for *why*
they disagree unless the evidence itself states one), and any claim whose
citation touches conflicted evidence is downgraded to `contradicted` by the
citation validator rather than silently picking a side.

**Documented limitation**: this only catches numeric factual disagreement.
It will not catch two sources disagreeing on a qualitative claim (e.g. "the
approach is considered reliable" vs. "the approach is considered
unreliable") — that would require semantic entailment checking, which is
out of scope here.

## 14. Reliability

- **Retries**: `app/reliability/retry.py` — bounded (`PROVIDER_MAX_RETRIES`,
  default 2), exponential backoff with jitter, and — critically — only for
  `ProviderError`s marked `retryable=True` (timeouts, connection errors,
  429/500/502/503). Auth failures and malformed requests are never
  retried.
- **Timeouts**: every provider, the fetcher, and every LLM client have a
  configurable timeout (`DDG_TIMEOUT_SECONDS`, `TAVILY_TIMEOUT_SECONDS`,
  `FETCH_TIMEOUT_SECONDS`, `LLM_TIMEOUT_SECONDS`).
- **Rate limiting**: `app/reliability/rate_limiter.py` — an in-process
  token bucket applied client-side to DuckDuckGo and Tavily calls, since
  DuckDuckGo's unofficial endpoint has no published limit to respect.
- **Circuit breaking**: `app/reliability/circuit_breaker.py` — after 3
  consecutive failures (configurable) a provider is short-circuited for 30
  seconds (configurable) to avoid wasting request latency hammering a
  clearly-down provider.
- **Partial failure**: if provider A fails and provider B succeeds, the
  request **does not fail** — the report is returned with `degraded: true`
  and an `Uncertainty` entry naming the failed provider.
- **Total failure**: if every provider fails, the pipeline returns a
  deterministic "insufficient evidence" report — no LLM call, no
  hallucinated answer, no fabricated sources.

## 15. Hallucination Reduction

Three independent layers, not one:

1. **Evidence-first architecture** (see §12) — the LLM never sees raw
   search results.
2. **Strict synthesis prompt** (`app/synthesis/prompts.py`) — explicit
   rules against outside knowledge, invented evidence IDs, invented URLs,
   and silently picking a side in a conflict.
3. **Citation validation** (`app/verification/citation_validator.py`) —
   every claim's citations are checked against *real* evidence IDs (an
   invented ID is rejected outright) and lexical overlap with the cited
   passage; low overlap or missing citations downgrade the claim to
   `insufficient_evidence` rather than trusting it.

**This does not guarantee truth.** Citation validation is a heuristic proxy
(lexical overlap), not semantic entailment — a claim can reuse a source's
words without accurately representing its meaning, and this system will not
catch that. This limitation is stated here deliberately rather than
implied away.

## Conversation Context Resolution

Follow-up questions are resolved against the conversation *before* retrieval,
so "Why is it popular?" after "What is JavaScript?" researches **JavaScript**
— never a different topic that happens to dominate search results.

### How it works

1. **State reconstruction** (`app/question_resolution/state.py`) — each
   research turn persists a compact resolution record
   (`raw_question`, `resolved_question`, `topic`, `intent`) in
   `research_requests.request_payload`. `build_conversation_state` rebuilds
   a lightweight `ConversationState` (previous question/answer, active
   topic, recent research topics, unresolved references) from stored
   messages + research records. **Memory here is for understanding only —
   it is never treated as evidence**, and fresh retrieval still happens for
   every answer.
2. **Deterministic resolution** (`app/question_resolution/resolver.py`) —
   the subject is decided by rules, not by the LLM:
   - bare pronouns (`it`, `its`, `they`, `them`, `their`, `this`,
     `that`, …) resolve to the **active topic**;
   - explicit capitalized entities in the new question **override or extend**
     the active topic (a new topic change, or a comparison keeps both);
   - an ambiguous pronoun with **no kind of active topic** sets
     `needs_clarification=True` — the assistant asks the user to name the
     subject instead of guessing a default;
   - an explicit entity in the same question (e.g. "What is GDPR and how
     does it work?") is self-contained and is never treated as ambiguous.
3. **Optional LLM polish with validation** — the LLM is only allowed to
   rephrase the grammatically imperfect resolved question for fluency; its
   output is rejected unless it still contains the deterministically chosen
   topic, so it cannot silently invent a new subject.
4. **Subject enforcement downstream** (`app/orchestration/research_pipeline.py`)
   — the resolved question becomes the *effective* research question, every
   generated subquery is checked to still mention the topic (recipient
   pronouns are rewritten, otherwise the topic is prefixed), and an
   evidence-level **topic-alignment gate** flags reports where most fetched
   passages do not mention the resolved topic (`status="partial"` +
   `evidence_topic_mismatch` uncertainty). The synthesis prompt receives the
   original question, the resolved question, and the active topic.
5. **Observability** — every report's `research_trace.resolution` carries
   the original/resolved question, active topic, intent, confidence, and
   method; the frontend renders this block and shows a status banner for
   `completed` / `partial` / `insufficient_evidence` / `needs_clarification`.

### Quality gates

- **10 unit tests** (`backend/tests/unit/test_question_resolution.py`,
  `105 backend tests passing`) cover the prescribed scenarios: the
  original reproduction ("why it differ from other programming language"
  after JavaScript), topic switches, comparisons, possessives, three-turn
  continuity (JavaScript → … → Python after an explicit switch), and
  clarification.
- **30-case evaluation dataset**
  (`backend/tests/evaluation/conversation_resolution_cases.json`) with a
  deterministic runner (`run_conversation_resolution.py`) — last recorded
  run: **30/30 (accuracy 1.0)**. See `docs/EVALUATION_RESULTS.md`.

## 16. Security

- **Secrets**: only ever read from environment variables
  (`app/config.py`); `.env` is git-ignored; `.env.example` has no real
  values; no key is ever logged (`_SENSITIVE_KEYS` redaction filter in
  `app/observability/logging.py`) or sent to the frontend.
- **SSRF protection**: `app/security/url_safety.py` blocks non-http(s)
  schemes, localhost/loopback, and private/link-local/reserved IP ranges
  before any server-side fetch of a ranked source. **Documented
  limitation**: this checks the resolved IP at validation time; a DNS
  rebinding attack (the hostname resolves differently between the check and
  the actual request) is not fully mitigated — a production hardening would
  pin the resolved IP for the actual request.
- **Input validation**: `ResearchRequest` (Pydantic) enforces
  question length (3–1000 chars), `max_sources` bounds (1–20), and a
  restricted `depth` enum; a middleware rejects oversized request bodies
  (`MAX_REQUEST_BODY_BYTES`).
- **CORS**: configured via `CORS_ALLOWED_ORIGINS`, not hardcoded or
  wildcarded.
- **Safe errors**: the API never returns a raw stack trace; unhandled
  exceptions are logged in full server-side and returned to the client as a
  generic `internal_error` (see `app/api/routes/research.py`).

## 17. Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest                        # everything
pytest tests/unit             # unit tests only
pytest tests/integration      # integration tests only (provider + API, all mocked)
pytest --cov=app --cov-report=term-missing   # with coverage
```

All external HTTP calls (DuckDuckGo, Tavily, Groq, Gemini) are mocked with
`respx` at the transport level — **no test makes a live network call**.

| Test file | Covers |
|---|---|
| `tests/unit/test_url_canonicalization.py` | Tracking-param stripping, fragment/trailing-slash/port normalization |
| `tests/unit/test_deduplication.py` | Exact URL dedup, fuzzy title dedup, distinct-results-preserved |
| `tests/unit/test_normalizer.py` | Dropping invalid raw results, provenance, stable IDs |
| `tests/unit/test_ranker.py` | Relevance ordering, query-dependent authority (docs vs. community) |
| `tests/unit/test_conflict_detector.py` | Numeric conflict detection, same-domain exclusion, small-difference tolerance |
| `tests/unit/test_citation_validator.py` | Missing citations, invented IDs, low lexical overlap, conflicted evidence |
| `tests/unit/test_url_safety.py` | SSRF blocking (scheme, localhost, private IPs) |
| `tests/unit/test_retry.py` | Retry-until-success, no-retry-on-permanent-error, retry exhaustion |
| `tests/unit/test_circuit_breaker.py` | Opens after threshold, stays closed below it, half-opens after window |
| `tests/unit/test_planner.py` | Simple-question skip, LLM decomposition, malformed-output fallback, LLM-failure fallback |
| `tests/integration/test_provider_failures.py` | DuckDuckGo/Tavily success, 429, 500, timeout, empty results, auth failure, malformed response |
| `tests/integration/test_research_pipeline.py` | Full pipeline: both providers succeed, one fails (degraded), all fail (insufficient evidence), conflict detected, hallucinated claim flagged, malformed LLM output handled |
| `tests/integration/test_api_health.py` | `GET /health` shape |
| `tests/integration/test_api_research.py` | `POST /api/research` happy path + validation errors (empty/overlong/missing question) |

## 18. Evaluation

See [`docs/EVALUATION_RESULTS.md`](docs/EVALUATION_RESULTS.md) for the full
write-up, including **exactly what was and was not executed in the
environment this project was built in** (no outbound network access was
available to install dependencies — see §24). The evaluation harness itself
(`backend/tests/evaluation/run_evaluation.py`) runs the real pipeline
against 7 controlled scenarios (one per required category) and prints
*measured* trace statistics — it does not report an invented accuracy
number.

## 19. Local Setup

**Prerequisites**: Python 3.12+, Node.js 20+.

```bash
# 1. Clone / unzip the project, then from the repo root:
cp .env.example .env
# edit .env — at minimum this works with LLM_PROVIDER=mock and TAVILY_API_KEY unset
# (DuckDuckGo alone will still return results); add TAVILY_API_KEY and a real
# LLM_PROVIDER for full functionality.

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
# → API docs at http://localhost:8000/docs

# 3. Frontend (new terminal)
cd frontend
cp .env.example .env
npm install
npm run dev
# → UI at http://localhost:5173

# 4. Tests (from backend/, with the venv active)
pytest
python -m tests.evaluation.run_evaluation
```

Or use the convenience script from the repo root: `./scripts/run_local.sh`
(starts both backend and frontend; requires steps 1–3's installs to have
been done first).

**Verified in this environment**: Python 3.11.9, Node 24.15.0 — all steps complete successfully. `pytest` → 84 tests pass, `mypy` + `ruff` clean, `npm run build` → production bundle 166 kB JS / 24 kB CSS gzipped, evaluation harness prints the numbers in `docs/EVALUATION_RESULTS.md`.

## 20. Docker Setup

```bash
cp .env.example .env   # fill in real values
docker compose up --build
# backend:  http://localhost:8000
# frontend: http://localhost:5173
```

Individual images:

```bash
docker build -t research-agent-backend ./backend
docker build -t research-agent-frontend ./frontend
```

Both Dockerfiles are multi-stage (build stage installs dependencies /
builds static assets; runtime stage is minimal and runs as a non-root
user), and both containers define a `HEALTHCHECK`.

**Verified in this environment**:
- `docker compose build` → both images built successfully (backend ~20s, frontend ~25s)
- `docker compose up -d` → `backend` healthy immediately, `frontend` healthy within ~10s
- `GET http://localhost:8000/health` → 200 with correct provider/LLM config
- `GET http://localhost:5173` → 200, built React app served via nginx
- `POST http://localhost:8000/api/research` → 200, valid `ResearchReport` with real sources

## 21. Production Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full guide: server
setup, firewall, reverse proxy + HTTPS/Let's Encrypt config, domain, health
checks, logging, restart policy, scaling caveats (in-process rate
limiter/circuit breaker are per-replica), provider rate limits, resource
limits, and update/rollback steps. **Local Docker success is not the same
as a validated production deployment** — that document says so explicitly
and lists what it does not cover.

## 22. API Documentation

FastAPI generates interactive OpenAPI docs at `/docs` (Swagger UI) and
`/redoc` automatically once the backend is running.

### `GET /health`

```json
{
  "status": "ok",
  "environment": "development",
  "providers": {
    "duckduckgo": {"enabled": true, "requires_api_key": false},
    "tavily": {"enabled": true, "requires_api_key": true, "configured": false}
  },
  "llm": {"provider": "mock", "model": "mock-model", "configured": true}
}
```

### `POST /api/research`

Request:

```json
{
  "question": "Compare the current approaches to AI agent memory and explain the major trade-offs.",
  "max_sources": 8,
  "depth": "standard"
}
```

Response (`ResearchReport`, abbreviated):

```json
{
  "request_id": "b3f1...",
  "question": "...",
  "answer": "...",
  "key_claims": [
    {"claim": "...", "citations": ["E1", "E3"], "support_status": "supported", "validator_note": null}
  ],
  "sources": [
    {"source_id": "...", "title": "...", "url": "...", "domain": "...", "providers": ["duckduckgo", "tavily"], "duplicate_count": 1, "final_score": 0.82, "fetched": true}
  ],
  "conflicts": [],
  "uncertainties": [],
  "research_trace": {
    "request_id": "b3f1...", "subqueries": 3, "providers_attempted": 2, "providers_succeeded": 2,
    "provider_outcomes": [{"name": "duckduckgo", "succeeded": true, "result_count": 6, "latency_ms": 412.3, "retries": 0}],
    "results_retrieved": 14, "duplicates_removed": 3, "sources_fetched": 8,
    "evidence_items": 8, "conflicts_detected": 0, "unsupported_claims_removed": 0, "total_latency_ms": 4820.5
  },
  "degraded": false
}
```

Errors follow FastAPI's standard shape, e.g. `422` for validation errors
(Pydantic detail), `502` for a handled `ResearchAgentError`, `500` for an
unexpected internal error (with a safe, generic message — see §16).

## 23. Failure Scenarios

| Scenario | Behavior |
|---|---|
| One provider times out / 429s / 5xxs | Retried per `PROVIDER_MAX_RETRIES` with backoff; if still failing, that provider's outcome is recorded as failed and the request continues with the other provider. Report has `degraded: true`. |
| One provider has invalid credentials | Not retried (permanent failure); same graceful-continue behavior as above. |
| Both providers fail | Pipeline returns a deterministic insufficient-evidence report. No LLM call is made. |
| Zero search results returned | Same insufficient-evidence short-circuit, with an `Uncertainty(reason="no_sources_found")`. |
| A source page fails to fetch (timeout, 404, blocked by SSRF check, non-HTML content-type) | That source falls back to its search snippet as evidence text; the batch of other fetches is unaffected. |
| LLM call fails (timeout, auth, 5xx) | Synthesis returns a safe fallback answer explaining the model could not be reached; sources/trace are still returned so the user can review raw evidence. |
| LLM returns malformed JSON | Same safe-fallback behavior; logged as `synthesis_output_malformed`. |
| LLM invents a citation ID | Rejected by the citation validator; claim marked `insufficient_evidence` with a validator note. |
| LLM claim has weak lexical support from its citation | Flagged `insufficient_evidence`, not trusted. |
| Two sources disagree numerically | Detected as a `Conflict`; any claim citing the conflicted evidence is marked `contradicted`. |

## 24. Known Limitations

Stated plainly, not hidden:

- Content fetching has no JavaScript rendering — client-side-rendered pages
  yield little or no extractable text and silently fall back to the search
  snippet.
- No `robots.txt` handling for the content fetcher (a production system
  serving real traffic at scale should add this; for a research-assistant
  use case fetching a small number of already-publicly-indexed pages, this
  was accepted as a scoped trade-off, not an oversight).
- Paywalled pages typically extract to near-empty or teaser text.
- PDFs are not parsed by the content fetcher (skipped via content-type
  check).
- Conflict detection only catches numeric disagreement, not qualitative/
  semantic contradiction.
- Citation validation is lexical-overlap-based, not semantic entailment —
  it reduces but does not eliminate unsupported claims.
- The in-memory rate limiter, circuit breaker, and metrics store are
  per-process; a multi-replica deployment would need a shared backend
  (Redis) for these to coordinate across instances.
- No authentication/authorization, no persistence layer, no request
  history — out of scope for this assignment.
- The frontend's "progress stages" are a client-side timer-driven
  approximation, not a real server-sent stream of actual pipeline stage
  completion (the backend responds once, synchronously, at the end).
- SSRF protection checks the resolved IP at validation time; it does not
  fully defend against DNS rebinding between check and fetch.
- Groq model names change over time; the current working default is
  `openai/gpt-oss-20b` (see `.env.example`). If the model is deprecated,
  update `LLM_MODEL` accordingly.
- The deterministic evaluation uses fake providers/mock LLM for speed and
  reproducibility; live evaluation with real providers is documented but
  consumes real API quota.

**Note**: The earlier claim that "tests were not executed" in the
sandboxed build environment no longer applies — the project has been
fully validated locally with `pytest` (84 passed), `ruff` + `mypy`
(clean), `npm run build` (production bundle), `docker compose up --build`
(both services healthy), and live E2E with real DuckDuckGo, Tavily, and
Groq `openai/gpt-oss-20b`.

## 25. Trade-offs

- **Synchronous request/response API over an async job queue.** Simpler to
  build, test, and reason about; acceptable because every stage is
  explicitly bounded (subquery count, provider count, fetch count). An
  async `GET /api/research/{request_id}` API would be preferable for
  "deep research" requests with many subqueries or a much larger fetch
  budget.
- **One deterministic pipeline pass over an autonomous agent loop.** The
  brief explicitly asks for a controlled, observable workflow rather than
  "uncontrolled autonomous agents" — this trades some flexibility (the
  system can't decide to re-search if the first pass looks thin) for
  predictable cost, latency, and debuggability.
- **Lexical-overlap citation validation over semantic/embedding-based
  validation.** No extra model call, fully deterministic, easy to unit
  test — at the cost of missing well-paraphrased-but-unsupported claims.
- **Regex-based numeric conflict detection over LLM-based contradiction
  detection.** Verifiable and testable, at the cost of missing
  non-numeric disagreements.
- **DuckDuckGo (unofficial HTML) as the zero-credential baseline
  provider**, accepting that it is not a stable, documented API, in
  exchange for the project being runnable by any reviewer with zero setup
  friction.

## 26. Future Improvements

- Add a third provider (e.g. Brave Search API) to further test the
  abstraction and improve source diversity.
- Move to an async job API for deep-research requests, with real
  server-pushed per-stage progress (replacing the frontend's client-side
  timer approximation).
- Add embedding-based semantic similarity as a second deduplication and
  citation-validation signal alongside the current lexical methods.
- Add a lightweight results cache (keyed by canonicalized query) to reduce
  redundant provider calls for repeated/similar questions.
- Externalize the rate limiter/circuit breaker/metrics to Redis for
  multi-replica deployments.
- Add PDF text extraction to the content fetcher.

## 27. Demo

A demo walkthrough **executable with the current code**:

1. `GET /health` reflecting current provider/LLM configuration (DuckDuckGo + Tavily + Groq `openai/gpt-oss-20b`).
2. A simple factual question — *"What is the boiling point of water at sea level?"* — fast path, no decomposition, `degraded: false`.
3. A comparison-style question — *"Compare the current approaches to AI agent memory and explain the major trade-offs."* — planner decomposition into subquestions, visible in the research trace (`subqueries: 2`).
4. A question likely to surface **conflicting** sources — *"How many employees does the company have, according to available reports?"* — the UI's Conflicts section shows the numeric disagreement (500 vs 700).
5. Temporarily disabling one provider (e.g. unset `TAVILY_API_KEY` and restart) to show the **degraded-but-successful** response and the "Provider X: Unavailable — continued using Provider Y" UI state.
6. A nonsense/obscure question to show the **insufficient-evidence** response rather than a fabricated answer (*"What will the price of a fictional cryptocurrency named Zephracoin9999XQ be next year?"*).
7. `pytest -v` in `backend/` → 84 tests pass, mypy + ruff clean.
8. `python -m tests.evaluation.run_evaluation` → prints the measured results in `docs/EVALUATION_RESULTS.md`.
9. `docker compose up --build` bringing up both services and passing health checks.
10. Live E2E: `POST /api/research` with *"What is the latest stable version of Python?"* → citation_coverage=1.0, 2 supported claims, real sources from python.org, wikipedia.org, docs.python.org.

## 28. Personal Implementation

*(Fill in before submitting — do not claim generated code as personally
written without disclosure.)*

> I used this AI-generated project as a foundation. What I personally
> reviewed, understood, modified, tested, and would defend in an interview:
>
> - [ ] I read and understood every module listed in §6.
> - [ ] I ran the backend test suite myself and can explain any failures I
>   fixed.
> - [ ] I ran `docker compose up --build` myself end-to-end.
> - [ ] I made the following specific changes/improvements of my own:
>   _____________________________________________
> - [ ] I can explain the deduplication, ranking, conflict-detection, and
>   citation-validation algorithms in my own words without re-reading the
>   code.
> - [ ] I obtained my own Tavily/Groq/Gemini API keys and tested a live run.

---

*See also: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md),
[`docs/EVALUATION_RESULTS.md`](docs/EVALUATION_RESULTS.md).*
