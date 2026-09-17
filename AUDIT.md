# ResearchLens Codebase Audit

**Date:** 2026-09-16  
**Auditor:** Principal AI Engineer / Staff Software Architect  
**Project:** ResearchLens - Multi-Source Web Research Agent (Zephra AI Assignment)

---

## Executive Summary

The existing codebase is a **well-architected, evidence-grounded research pipeline** with strong engineering fundamentals. It successfully implements:

- Multi-source retrieval (DuckDuckGo, Tavily, Brave) with provider abstraction
- Deterministic pipeline: plan → retrieve → normalize → dedupe → rank → fetch → evidence → conflicts → synthesize → validate
- Deterministic conflict detection (numeric) and citation validation (lexical overlap)
- Robust reliability: retry/backoff, circuit breakers, rate limiting, graceful degradation
- Clean async FastAPI architecture with structured logging, request-ID correlation
- 84 passing tests (unit + integration) with mocked external dependencies
- Docker support with health checks, multi-stage builds

**However**, the current implementation is a **single-shot request/response tool** — not a conversational research workspace. It lacks:

- **Persistence** (no database, no conversation history)
- **Conversation model** (no sessions, no message history)
- **Memory layer** (no follow-up question support, no context resolution)
- **Conversational UI** (no sidebar, no chat history, no evidence drawer)
- **Session management** (no resume, no search, no rename/delete)

---

## Detailed Architecture Audit

### ✅ Strengths (Production-Ready)

| Component | Assessment | Notes |
|-----------|------------|-------|
| **Provider Abstraction** | Excellent | Clean `SearchProvider` interface; adding Brave took 1 file + 1 line in main.py |
| **Retrieval Orchestration** | Excellent | Parallel (query × provider) with semaphore, retry, circuit breaker |
| **Normalization** | Good | Canonical URL (tracking params, fragment, trailing slash, ports) |
| **Deduplication** | Excellent | Two-stage: exact URL + fuzzy title (0.95) with numeric conflict guard |
| **Ranking** | Good | 0.5×relevance + 0.3×authority + 0.2×freshness; query-dependent authority |
| **Content Fetching** | Good | SSRF protection, bounded size/timeout, snippet fallback |
| **Evidence Building** | Good | Query-aware passage extraction; grounded passages only |
| **Conflict Detection** | Good | Deterministic regex-based numeric conflicts (>2% diff, cross-domain) |
| **Citation Validation** | Good | ID existence + lexical overlap (0.15) + conflict awareness |
| **Reliability** | Excellent | Retry (2, exp backoff), circuit breaker (3/30s), rate limiting (token bucket) |
| **Security** | Good | SSRF protection, input validation, secret redaction, safe errors |
| **Tests** | Excellent | 84 tests (45 unit + 39 integration), all mocked, mypy/ruff clean |
| **Documentation** | Excellent | Comprehensive README, DEPLOYMENT.md, EVALUATION_RESULTS.md |

### ⚠️ Known Limitations (Documented)

1. **No JS rendering** — CSR pages fall back to snippet
2. **No robots.txt** — Scoped trade-off
3. **No PDF parsing** — Content-type check skips
4. **Conflict detection = numeric only** — No semantic entailment
5. **Citation validation = lexical** — Not semantic
6. **In-memory rate limiter/circuit breaker** — Per-process, needs Redis for multi-replica
6. **No auth/persistence/history** — Explicitly out of scope
7. **Progress stages = client timer** — Not server-streamed
8. **SSRF = DNS rebinding possible** — Check at validation time only
9. **Groq model drift** — Model names change over time

---

## ❌ Critical Gaps for Conversational Workspace

### 1. No Persistence Layer
- **No database** — SQLite/PostgreSQL not implemented
- **No conversation storage** — Cannot resume sessions after refresh
- **No message history** — Cannot show previous Q&A

### 2. No Conversation Model
```python
# Current: Single ResearchRequest → ResearchReport
# Needed:
Conversation { id, title, created_at, updated_at, status }
Message { id, conversation_id, role, content, research_request_id?, created_at }
ResearchRequest { id, conversation_id, question, status, created_at }
ResearchResult { id, research_request_id, answer, claims, sources, evidence, conflicts, trace }
```

### 3. No Memory/Context Layer
- **No follow-up resolution** — "What about security?" → needs context from previous turn
- **Memory ≠ Evidence** — Architecture must separate:
  - `ConversationContext` (recent messages for intent)
  - `MemoryContext` (entities, topics, scope from history)
  - `EvidenceContext` (freshly retrieved, verified passages only)

### 4. No Conversational UI
- **No sidebar** — No conversation list, search, new/resume
- **No chat view** — Single report, not conversational messages
- **No evidence drawer** — Citations not interactive
- **No sticky composer** — Must scroll to bottom
- **No conversation management** — No rename, delete, archive

---

## Frontend Architecture Audit

### Current State
- React 18 + TypeScript + Vite + Tailwind
- Single-page app: `App.tsx` manages all state
- Components: `QueryInput`, `AnswerView`, `ConflictsView`, `SourcesList`, `ResearchTrace`, `SystemStatus`, `Header`, `ProgressStages`
- API client: `runResearch`, `checkHealth`, `getProviderStatus`

### Missing for Conversational Workspace
1. **Sidebar component** — Conversation list, search, new research button
2. **Conversation list item** — Title, timestamp, source count, status
3. **Chat message components** — User message, assistant message (with embedded report)
4. **Evidence drawer** — Right-side slide-out with interactive citations
5. **Sticky composer** — Fixed bottom, Enter/Shift+Enter, disabled during loading
6. **Conversation management** — Context menu for rename/delete
7. **Search/filter** — Conversation search in sidebar
8. **State management** — Conversation list, active conversation, messages

---

## Backend API Changes Needed

### New Endpoints
```
GET    /api/conversations              # List conversations (with pagination/search)
POST   /api/conversations              # Create new conversation
GET    /api/conversations/{id}         # Get conversation with messages
PATCH  /api/conversations/{id}         # Rename, archive
DELETE /api/conversations/{id}         # Delete conversation
GET    /api/conversations/{id}/messages # Get messages for conversation
POST   /api/conversations/{id}/messages # Add message (triggers research for user messages)
POST   /api/conversations/{id}/research # Trigger research with context resolution
```

### Modified Endpoint
```
POST /api/research  # Accept optional conversation_id for context
```

---

## Database Schema (SQLite for Simplicity)

```sql
-- Conversations
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active, archived
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Messages
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,  -- 'user' | 'assistant'
    content TEXT NOT NULL,  -- JSON for assistant (ResearchReport), text for user
    research_request_id TEXT,  -- Links to research request if applicable
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Research Requests (for traceability)
CREATE TABLE research_requests (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, completed, failed
    request_payload TEXT,  -- JSON of ResearchRequest
    response_payload TEXT,  -- JSON of ResearchReport
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX idx_research_conversation ON research_requests(conversation_id);
```

---

## Memory/Context Resolution Architecture

### For Follow-Up Questions:
```
User: "Compare RAG and fine-tuning"
  → ResearchRequest(question="Compare RAG and fine-tuning")
  → ResearchReport(answer, claims, sources, conflicts, trace)

User: "What about security risks?"
  → Context Resolution:
      1. Get last N messages from conversation
      2. Extract entities/topics: ["RAG", "fine-tuning", "enterprise AI"]
      3. Resolve: "What are the security risks of RAG and fine-tuning for enterprise AI?"
  → ResearchRequest(question="What are the security risks of RAG and fine-tuning for enterprise AI?")
  → ResearchReport (fresh retrieval, fresh evidence, fresh citations)
```

### Memory Types (Separate from Evidence):
1. **ConversationContext** — Last 3-5 messages for pronoun/coreference resolution
2. **ResearchContext** — Entities, topics, scope extracted from previous turns
3. **UserPreferences** — Only if explicitly provided

**Critical Rule:** Memory helps form better queries. **Only freshly retrieved evidence supports claims.**

---

## Implementation Plan (Phased)

### Phase 1: Backend Foundation (Week 1)
- [ ] Add SQLAlchemy + SQLite (dev) / PostgreSQL (prod) models
- [ ] Create Alembic migrations
- [ ] Implement conversation/message/research_request repositories
- [ ] Add conversation API routes (CRUD + messages)
- [ ] Add context resolution service for follow-up questions
- [ ] Modify `/api/research` to accept `conversation_id` and use context
- [ ] Unit/integration tests for new endpoints

### Phase 2: Frontend Shell (Week 1-2)
- [ ] Add React Router for conversation routes
- [ ] Build persistent Sidebar component (collapsible, searchable)
- [ ] Build ConversationList with search/filter
- [ ] Build ChatView with message rendering
- [ ] Build sticky Composer with Enter/Shift+Enter
- [ ] Integrate with new API endpoints
- [ ] State management for conversations + active conversation

### Phase 3: Conversational Features (Week 2)
- [ ] Follow-up question handling (context resolution)
- [ ] Evidence drawer (right-side, interactive citations)
- [ ] Conversation management (new, rename, delete, archive)
- [ ] Conversation search in sidebar
- [ ] Auto-title generation from first question
- [ ] Loading states, error handling, empty states

### Phase 4: Polish & Validation (Week 2-3)
- [ ] Real-time provider status in sidebar
- [ ] Related research suggestions
- [ ] Copy/export research report
- [ ] Mobile responsive (drawer sidebar)
- [ ] Accessibility (keyboard nav, ARIA, reduced motion)
- [ ] Run full test suite
- [ ] Docker validation
- [ ] Documentation updates

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Database migration complexity | Medium | High | Use SQLite for dev, SQLAlchemy + Alembic |
| Context resolution quality | Medium | High | Start simple (last 3 messages + entity extraction) |
| Frontend state complexity | High | High | Use React Context + useReducer, keep it simple |
| Evidence drawer UX | Medium | Medium | Build iteratively, test with real citations |
| Follow-up query relevance | Medium | High | Log resolved queries for debugging |
| Performance with history | Low | Medium | Paginate conversations, limit message context |

---

## Recommendation

**Proceed with implementation.** The existing pipeline is production-quality and provides a solid foundation. The conversational layer is additive — it wraps the existing pipeline without modifying its core evidence-grounded architecture.

**Key principle to maintain:** Memory helps form queries; only fresh evidence supports claims. This architectural boundary must be enforced in code, not just documentation.

---

## Files to Create/Modify (Summary)

### Backend New Files
- `backend/app/models/conversation.py` — SQLAlchemy models
- `backend/app/repositories/conversation_repo.py` — Data access
- `backend/app/services/context_resolver.py` — Follow-up resolution
- `backend/app/api/routes/conversations.py` — New endpoints
- `backend/alembic/` — Migrations

### Backend Modified Files
- `backend/app/main.py` — Include new router
- `backend/app/api/routes/research.py` — Accept conversation_id
- `backend/app/orchestration/research_pipeline.py` — Accept context
- `backend/app/config.py` — Database URL setting

### Frontend New Files
- `frontend/src/components/Sidebar.tsx`
- `frontend/src/components/ConversationList.tsx`
- `frontend/src/components/ConversationItem.tsx`
- `frontend/src/components/ChatView.tsx`
- `frontend/src/components/Message.tsx`
- `frontend/src/components/EvidenceDrawer.tsx`
- `frontend/src/components/Composer.tsx`
- `frontend/src/hooks/useConversations.ts`
- `frontend/src/hooks/useChat.ts`
- `frontend/src/pages/ConversationPage.tsx`

### Frontend Modified Files
- `frontend/src/App.tsx` — Router + sidebar layout
- `frontend/src/api/client.ts` — New API functions
- `frontend/src/types.ts` — Conversation/Message types
- `frontend/src/styles/index.css` — New component styles