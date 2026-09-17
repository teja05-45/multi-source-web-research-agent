export interface ResearchRequest {
  question: string;
  max_sources?: number;
  providers?: string[];
  depth?: "quick" | "standard";
}

export type SupportStatus = "supported" | "contradicted" | "insufficient_evidence";

export interface VerifiedClaim {
  claim: string;
  citations: string[];
  support_status: SupportStatus;
  validator_note?: string | null;
}

export interface SourceSummary {
  source_id: string;
  title: string;
  url: string;
  domain: string;
  providers: string[];
  duplicate_count: number;
  final_score: number;
  fetched: boolean;
}

export interface Conflict {
  topic: string;
  position_a: string;
  position_a_sources: string[];
  position_b: string;
  position_b_sources: string[];
  possible_explanation?: string | null;
}

export interface Uncertainty {
  description: string;
  reason: string;
}

export interface ProviderOutcome {
  name: string;
  succeeded: boolean;
  result_count: number;
  error?: string | null;
  latency_ms?: number | null;
  retries: number;
}

export type ReportStatus =
  | "completed"
  | "partial"
  | "insufficient_evidence"
  | "needs_clarification";

export interface Resolution {
  raw_question: string;
  resolved_question: string;
  topic?: string | null;
  is_follow_up: boolean;
  intent: string;
  referenced_entities: string[];
  confidence: number;
  needs_clarification: boolean;
  method: string;
}

export interface ResearchTrace {
  request_id: string;
  subqueries: number;
  providers_attempted: number;
  providers_succeeded: number;
  provider_outcomes: ProviderOutcome[];
  results_retrieved: number;
  duplicates_removed: number;
  sources_fetched: number;
  evidence_items: number;
  conflicts_detected: number;
  unsupported_claims_removed: number;
  citation_coverage: number;
  stage_timings_ms: Record<string, number>;
  total_latency_ms?: number | null;
  resolution?: Resolution | null;
}

export interface ResearchReport {
  request_id: string;
  question: string;
  answer: string;
  key_claims: VerifiedClaim[];
  sources: SourceSummary[];
  conflicts: Conflict[];
  uncertainties: Uncertainty[];
  research_trace: ResearchTrace;
  degraded: boolean;
  status: ReportStatus;
}

export interface ProviderStatus {
  name: string;
  configured: boolean;
  enabled: boolean;
  circuit_breaker_state?: string;
  circuit_breaker_failure_count?: number;
}

export interface Evidence {
  evidence_id: string;
  source_id: string;
  url: string;
  title: string;
  domain: string;
  passage: string;
  relevance_score: number;
  authority_score: number;
  freshness_score: number;
  final_score: number;
  from_fetched_content: boolean;
}

// --- Conversation Types ---

export type ConversationStatus = "active" | "archived";

export interface Conversation {
  id: string;
  title: string;
  status: ConversationStatus;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export type MessageRole = "user" | "assistant";

export interface Message {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  research_request_id?: string | null;
  created_at: string;
}

export interface ConversationCreate {
  title: string;
}

export interface ConversationUpdate {
  title?: string;
  status?: ConversationStatus;
}

export interface MessageCreate {
  role: MessageRole;
  content: string;
  research_request_id?: string | null;
}

export interface ResearchRequestCreate {
  question: string;
  max_sources?: number;
  providers?: string[];
  depth?: "quick" | "standard";
}

export interface ResolvedContext {
  original_question: string;
  resolved_question: string;
  entities: string[];
  topics: string[];
  scope: string;
  used_fallback: boolean;
}