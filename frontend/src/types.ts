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
}

export interface ProviderStatus {
  name: string;
  configured: boolean;
  enabled: boolean;
  circuit_breaker_state?: string;
  circuit_breaker_failure_count?: number;
}