import { useState } from "react";
import { formatPercent } from "../lib/format";
import type { ResearchTrace, VerifiedClaim } from "../types";

interface Props {
  answer: string;
  keyClaims: VerifiedClaim[];
  trace: ResearchTrace;
  degraded: boolean;
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

export default function AnswerView({ answer, keyClaims, trace, degraded }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const coverage = trace.citation_coverage;

  return (
    <article className="card p-6 sm:p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="section-label mb-1">Answer</p>
          <h2 className="text-xl font-semibold text-gray-900">Synthesis</h2>
        </div>
        <button onClick={handleCopy} className="btn-secondary text-xs py-1.5 px-3">
          {copied ? "Copied" : "Copy answer"}
        </button>
      </div>

      {degraded && (
        <div className="mt-3 text-xs inline-flex items-center gap-1.5 bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-1 rounded-full">
          <span aria-hidden="true">!</span> Partial source coverage — one or more providers were unavailable
        </div>
      )}

      <div className="mt-5 flex items-center gap-3">
        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden" aria-hidden="true">
          <div
            className="h-full bg-gradient-to-r from-emerald-500 to-accent-500 rounded-full"
            style={{ width: `${Math.min(100, coverage * 100)}%` }}
          />
        </div>
        <span className="text-xs text-gray-500 whitespace-nowrap">
          {formatPercent(coverage)} of claims cited
        </span>
      </div>

      <p className="mt-5 text-gray-800 leading-relaxed text-[1.0625rem]">{answer}</p>

      {keyClaims.length > 0 && (
        <div className="mt-7">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Key claims</h3>
          <ul className="space-y-2.5">
            {keyClaims.map((claim, i) => (
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
    </article>
  );
}