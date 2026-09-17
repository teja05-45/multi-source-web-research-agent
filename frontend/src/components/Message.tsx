import { formatDistanceToNow } from "date-fns";
import { copyToClipboard } from "../lib/format";
import type { Message, ResearchReport } from "../types";

interface Props {
  message: Message;
}

export default function Message({ message }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[75%]">
          <div className="bg-accent-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
            <p className="text-sm leading-relaxed">{message.content}</p>
          </div>
          <p className="text-xs text-gray-400 text-right mt-1">
            {formatDistanceToNow(new Date(message.created_at), { addSuffix: true })}
          </p>
        </div>
      </div>
    );
  }

  let report: ResearchReport | null = null;
  let errorEnvelope: { error: { code: string; message: string; request_id: string; retryable?: boolean } } | null = null;
  try {
    const parsed = JSON.parse(message.content);
    if (parsed?.error && typeof parsed.error === "object") {
      errorEnvelope = parsed;
    } else {
      report = parsed as ResearchReport;
    }
  } catch {
    report = null;
  }

  if (errorEnvelope) {
    const { code, request_id, retryable } = errorEnvelope.error;
    const errorMessage = errorEnvelope.error.message;
    return (
      <div className="flex justify-start mb-4">
        <div className="max-w-[85%]">
          <div className="bg-white border border-red-200 rounded-2xl rounded-tl-sm overflow-hidden shadow-sm">
            <div className="px-5 py-4 border-b border-red-100 bg-red-50/60">
              <div className="flex items-center gap-2 text-red-700 font-semibold text-sm">
                <span aria-hidden="true">!</span> Research could not be completed
              </div>
            </div>
            <div className="px-5 py-4">
              <p className="text-sm text-gray-800 leading-relaxed">{errorMessage}</p>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                <span className={`px-2 py-0.5 rounded-full border ${retryable ? "bg-amber-50 border-amber-200 text-amber-700" : "bg-gray-100 border-gray-200 text-gray-600"}`}>
                  {retryable ? "Retryable" : "Not retryable"}
                </span>
                <span className="px-2 py-0.5 rounded-full bg-gray-100 border border-gray-200 text-gray-600 font-mono">
                  {code}
                </span>
                <span className="ml-auto font-mono">req: {request_id.slice(0, 8)}</span>
              </div>
            </div>
          </div>
          <p className="text-xs text-gray-400 ml-1 mt-1">
            {formatDistanceToNow(new Date(message.created_at), { addSuffix: true })}
          </p>
        </div>
      </div>
    );
  }

  const STATUS_STYLES: Record<string, string> = {
    supported: "bg-emerald-50 text-emerald-700 border-emerald-200",
    contradicted: "bg-amber-50 text-amber-700 border-amber-200",
    insufficient_evidence: "bg-gray-100 text-gray-600 border-gray-200",
  };

  const STATUS_LABELS: Record<string, string> = {
    supported: "Supported",
    contradicted: "Conflicting",
    insufficient_evidence: "Unverified",
  };

  if (!report) {
    return (
      <div className="flex justify-start mb-4">
        <div className="max-w-[85%]">
          <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
            <p className="text-gray-800">{message.content}</p>
          </div>
          <p className="text-xs text-gray-400 ml-1 mt-1">
            {formatDistanceToNow(new Date(message.created_at), { addSuffix: true })}
          </p>
        </div>
      </div>
    );
  }

  const coverage = report.research_trace.citation_coverage;

  const handleCopy = async () => {
    await copyToClipboard(report.answer);
  };

  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[85%]">
        <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm overflow-hidden shadow-sm">
          <div className="flex items-start justify-between gap-4 p-5 border-b border-gray-200 bg-gray-50/50">
            <div>
              <p className="section-label mb-1">Answer</p>
              <h2 className="text-xl font-semibold text-gray-900">Synthesis</h2>
            </div>
            <button onClick={handleCopy} className="btn-secondary text-xs py-1.5 px-3">
              Copy answer
            </button>
          </div>

          {report.degraded && (
            <div className="px-5 py-3 border-b border-gray-200 bg-amber-50/50">
              <div className="text-xs inline-flex items-center gap-1.5 bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-1 rounded-full">
                <span aria-hidden="true">!</span> Partial source coverage — one or more providers were unavailable
              </div>
            </div>
          )}

          {report.status === "partial" && (
            <div className="px-5 py-3 border-b border-gray-200 bg-amber-50/50">
              <p className="text-xs text-amber-800">
                Partial answer — some evidence was missing, conflicted, or failed verification. See the
                uncertainty notes below for details.
              </p>
            </div>
          )}

          {report.status === "insufficient_evidence" && (
            <div className="px-5 py-3 border-b border-gray-200 bg-gray-100/60">
              <p className="text-xs text-gray-600">
                Insufficient evidence — no reliable sources were found for this question. The system
                did not guess an answer.
              </p>
            </div>
          )}

          {report.status === "needs_clarification" && (
            <div className="px-5 py-3 border-b border-gray-200 bg-accent-50/60">
              <p className="text-xs text-accent-800">
                Needs clarification — the question referenced an unknown subject, so the assistant asked
                the user to name it explicitly instead of guessing.
              </p>
            </div>
          )}

          <div className="p-5">
            <p className="text-gray-800 leading-relaxed text-[1.0625rem]">{report.answer}</p>
          </div>

          <div className="px-5 pb-5">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden" aria-hidden="true">
                <div
                  className="h-full bg-gradient-to-r from-emerald-500 to-accent-500 rounded-full"
                  style={{ width: `${Math.min(100, coverage * 100)}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap">
                {Math.round(coverage * 100)}% of claims cited
              </span>
            </div>
          </div>

          {report.key_claims.length > 0 && (
            <div className="px-5 pb-5 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Key claims</h3>
              <ul className="space-y-2.5">
                {report.key_claims.map((claim, i) => (
                  <li key={i} className="flex items-start gap-3 text-sm bg-gray-50/70 rounded-xl px-3.5 py-2.5">
                    <span
                      className={`shrink-0 mt-0.5 text-[11px] font-medium px-2 py-0.5 rounded-full border ${STATUS_STYLES[claim.support_status]}`}
                    >
                      {STATUS_LABELS[claim.support_status]}
                    </span>
                    <span className="text-gray-800">
                      {claim.claim}
                      {claim.citations.length > 0 && (
                        <span className="text-gray-400">
                          {" "}
                          · cites {claim.citations.join(", ")}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.conflicts.length > 0 && (
            <div className="px-5 py-5 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Conflicts</h3>
              <ul className="space-y-3">
                {report.conflicts.map((c, i) => (
                  <li key={i} className="rounded-xl border border-amber-200 bg-amber-50/70 p-4 text-sm">
                    <div className="font-medium text-amber-800 mb-1">Disagreement about: {c.topic}</div>
                    <div className="text-gray-700">
                      <span className="font-medium">{c.position_a_sources.join(", ")}:</span> {c.position_a}
                    </div>
                    <div className="text-gray-700 mt-1">
                      <span className="font-medium">{c.position_b_sources.join(", ")}:</span> {c.position_b}
                    </div>
                    {c.possible_explanation && (
                      <div className="mt-2 text-xs text-gray-500">
                        Possible explanation: {c.possible_explanation}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.uncertainties.length > 0 && (
            <div className="px-5 py-5 border-b border-gray-200">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Uncertainty</h3>
              <ul className="space-y-2 text-sm text-gray-700">
                {report.uncertainties.map((u, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full bg-gray-100 border border-gray-200 text-gray-600">
                      {u.reason.replace(/_/g, " ")}
                    </span>
                    <span>{u.description}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="px-5 py-5">
            <div className="flex items-baseline justify-between mb-4">
              <p className="section-label">Sources</p>
              <span className="text-sm text-gray-400">{report.sources.length}</span>
            </div>
            {report.sources.length === 0 ? (
              <p className="text-sm text-gray-500">No sources were retrieved for this request.</p>
            ) : (
              <ul className="grid gap-3 md:grid-cols-2">
                {report.sources.map((source) => (
                  <li key={source.source_id} className="rounded-xl border border-gray-200 p-4 hover:border-accent-200 hover:shadow-sm transition-all">
                    <div className="flex items-start gap-3">
                      <div
                        aria-hidden="true"
                        className="shrink-0 w-9 h-9 rounded-lg bg-gradient-to-br from-accent-500 to-accent-700 text-white text-sm font-semibold flex items-center justify-center"
                      >
                        {source.domain.replace(/^www\./, "")[0]?.toUpperCase() || "?"}
                      </div>
                      <div className="min-w-0">
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-700 font-medium text-sm leading-snug hover:underline break-words"
                        >
                          {source.title}
                        </a>
                        <div className="flex flex-wrap items-center gap-2 mt-1.5 text-xs text-gray-500">
                          <span>{source.domain}</span>
                          <span>·</span>
                          <span>score {source.final_score.toFixed(2)}</span>
                          {source.fetched && (
                            <>
                              <span aria-hidden="true">·</span>
                              <span className="text-emerald-600 font-medium">fetched</span>
                            </>
                          )}
                          {source.duplicate_count > 0 && (
                            <>
                              <span aria-hidden="true">·</span>
                              <span>{source.duplicate_count} merged</span>
                            </>
                          )}
                          <span aria-hidden="true">·</span>
                          <span className="text-gray-400">via {source.providers.join(", ")}</span>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="px-5 pb-5">
            <button
              onClick={() => {}}
              className="flex items-center justify-between w-full text-left p-3 rounded-xl bg-gray-50 hover:bg-gray-100 transition-colors"
            >
              <div>
                <p className="section-label mb-1">Diagnostics</p>
                <h3 className="text-lg font-semibold text-gray-900">Research trace</h3>
              </div>
              <span className="text-sm text-gray-400">Show</span>
            </button>
          </div>
        </div>

        <p className="text-xs text-gray-400 text-center px-5 pb-5">
          End of response
        </p>
      </div>
    </div>
  );
}