import { useState } from "react";
import { formatMs } from "../lib/format";
import type { ResearchTrace as ResearchTraceType } from "../types";

interface Props {
  trace: ResearchTraceType;
}

export default function ResearchTrace({ trace }: Props) {
  const [expanded, setExpanded] = useState(false);

  const stages = Object.entries(trace.stage_timings_ms ?? {}).sort((a, b) => b[1] - a[1]);
  const maxStage = stages[0]?.[1] ?? 0;

  return (
    <div className="card p-6 sm:p-8">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center justify-between w-full text-left group"
        aria-expanded={expanded}
        aria-controls="research-trace-panel"
      >
        <div>
          <p className="section-label mb-1">Diagnostics</p>
          <h2 className="text-lg font-semibold text-gray-900">Research trace</h2>
        </div>
        <span className="text-sm text-gray-400 group-hover:text-gray-600 transition-colors">
          {expanded ? "Hide" : "Show"}
        </span>
      </button>

      {expanded && (
        <div id="research-trace-panel" className="mt-6 space-y-6">
          {trace.resolution && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Question resolution</h3>
              <div className="rounded-xl border border-gray-200 bg-gray-50/70 p-4 text-sm space-y-2">
                {trace.resolution.is_follow_up && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-accent-50 text-accent-700 border border-accent-200">
                      follow-up
                    </span>
                    <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200 capitalize">
                      {trace.resolution.intent.replace(/_/g, " ")}
                    </span>
                    {trace.resolution.topic && (
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                        topic: {trace.resolution.topic}
                      </span>
                    )}
                  </div>
                )}
                <div className="grid sm:grid-cols-2 gap-3">
                  <div className="bg-white rounded-lg border border-gray-200 p-3">
                    <div className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">Original question</div>
                    <div className="text-gray-800">{trace.resolution.raw_question}</div>
                  </div>
                  <div className="bg-white rounded-lg border border-gray-200 p-3">
                    <div className="text-[11px] text-gray-400 uppercase tracking-wide mb-1">Resolved question</div>
                    <div className="text-gray-800 font-medium">{trace.resolution.resolved_question}</div>
                  </div>
                </div>
                {trace.resolution.needs_clarification && (
                  <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    The subject could not be resolved — the assistant asked the user to clarify.
                  </p>
                )}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            <TraceStat label="Subqueries" value={trace.subqueries} />
            <TraceStat label="Providers succeeded" value={`${trace.providers_succeeded}/${trace.providers_attempted}`} />
            <TraceStat label="Results retrieved" value={trace.results_retrieved} />
            <TraceStat label="Duplicates removed" value={trace.duplicates_removed} />
            <TraceStat label="Sources fetched" value={trace.sources_fetched} />
            <TraceStat label="Evidence items" value={trace.evidence_items} />
            <TraceStat label="Conflicts detected" value={trace.conflicts_detected} />
            <TraceStat label="Unsupported claims removed" value={trace.unsupported_claims_removed} />
            <TraceStat label="Citation coverage" value={`${Math.round((trace.citation_coverage ?? 0) * 100)}%`} />
            <TraceStat label="Total latency" value={formatMs(trace.total_latency_ms)} />
            <TraceStat label="Request ID" value={trace.request_id.slice(0, 8)} />
          </div>

          {stages.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Stage timings</h3>
              <ul className="space-y-2">
                {stages.map(([stage, ms]) => (
                  <li key={stage} className="flex items-center gap-3 text-xs">
                    <span className="w-32 shrink-0 text-gray-500 capitalize">{stage.replace(/_/g, " ")}</span>
                    <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden" aria-hidden="true">
                      <div
                        className="h-full bg-accent-500 rounded-full"
                        style={{ width: `${maxStage ? (ms / maxStage) * 100 : 0}%` }}
                      />
                    </div>
                    <span className="w-14 shrink-0 text-right text-gray-500 tabular-nums">{formatMs(ms)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {trace.provider_outcomes.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Provider outcomes</h3>
              <ul className="space-y-2">
                {trace.provider_outcomes.map((p) => (
                  <li
                    key={p.name}
                    className={`text-xs px-3 py-2 rounded-lg border ${
                      p.succeeded
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : "border-red-200 bg-red-50 text-red-700"
                    }`}
                  >
                    <span className="font-medium capitalize">{p.name}</span>{" "}
                    {p.succeeded
                      ? `— ${p.result_count} results, ${formatMs(p.latency_ms)}, ${p.retries} retries`
                      : `— Unavailable: ${p.error ?? "unknown error"} — continued using other providers`}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-xs text-gray-400">
            Pipeline may retry individual steps; `stage_timings_ms` measures wall-clock time per phase.
          </p>
        </div>
      )}
    </div>
  );
}

function TraceStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2">
      <div className="text-gray-400 text-xs">{label}</div>
      <div className="text-gray-900 font-medium">{value}</div>
    </div>
  );
}