import { useState, useEffect } from "react";
import type { VerifiedClaim, Evidence } from "../types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  claim?: VerifiedClaim;
  evidenceMap: Map<string, Evidence>;
}

export default function EvidenceDrawer({ isOpen, onClose, claim, evidenceMap }: Props) {
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);

  const evidence = claim?.citations
    .map((id) => evidenceMap.get(id))
    .filter((e): e is NonNullable<typeof e> => e !== undefined) || [];

  // Auto-select first evidence when claim changes
  useEffect(() => {
    if (evidence.length > 0) {
      setSelectedEvidenceId(evidence[0].evidence_id);
    } else {
      setSelectedEvidenceId(null);
    }
  }, [evidence]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true" aria-label="Evidence">
      <div
        className="absolute inset-0 bg-gray-900/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="relative w-full max-w-2xl h-full bg-white flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 sticky top-0 bg-white z-10">
          <div>
            <p className="section-label mb-1">Evidence</p>
            <h2 className="text-lg font-semibold text-gray-900">
              {claim ? "Supporting Evidence" : "Select a claim"}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="btn-secondary text-xs py-1.5 px-2.5"
            aria-label="Close evidence drawer"
          >
            Close
          </button>
        </div>

        {/* Evidence List */}
        <div className="flex-1 overflow-y-auto p-4">
          {claim ? (
            <div className="space-y-3">
              <div className="mb-4 p-3 bg-gray-50 rounded-lg">
                <p className="text-sm font-medium text-gray-700 mb-1">Claim</p>
                <p className="text-sm text-gray-800">{claim.claim}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {claim.citations.map((citationId) => (
                    <button
                      key={citationId}
                      onClick={() => setSelectedEvidenceId(citationId)}
                      className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                        selectedEvidenceId === citationId
                          ? "bg-accent-600 text-white border-accent-600"
                          : "bg-gray-100 text-gray-600 border-gray-200 hover:bg-gray-200"
                      }`}
                    >
                      {citationId}
                    </button>
                  ))}
                </div>
              </div>

              {evidence.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-8">No evidence available for this claim.</p>
              ) : (
                <ul className="space-y-3" role="list" aria-label="Evidence sources">
                  {evidence.map((ev) => (
                    <li
                      key={ev.evidence_id}
                      className={`rounded-xl border p-4 transition-all ${
                        selectedEvidenceId === ev.evidence_id
                          ? "border-accent-300 bg-accent-50/50 shadow-sm"
                          : "border-gray-200 hover:border-accent-200"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <button
                          onClick={() => setSelectedEvidenceId(ev.evidence_id)}
                          className={`shrink-0 w-2.5 h-2.5 rounded-full border-2 transition-colors ${
                            selectedEvidenceId === ev.evidence_id
                              ? "bg-accent-600 border-accent-600"
                              : "border-gray-300 hover:border-accent-400"
                          }`}
                          aria-pressed={selectedEvidenceId === ev.evidence_id}
                          aria-label={selectedEvidenceId === ev.evidence_id ? "Selected" : "Select"}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline gap-2 mb-1">
                            <a
                              href={ev.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-accent-700 font-medium text-sm hover:underline truncate block"
                            >
                              {ev.title}
                            </a>
                            <span className="text-xs text-gray-400">{ev.domain}</span>
                            <span className="text-xs text-gray-400">·</span>
                            <span className="text-xs text-gray-400">Score: {ev.final_score.toFixed(2)}</span>
                            {ev.from_fetched_content && (
                              <span className="text-xs text-emerald-600 font-medium">Fetched</span>
                            )}
                          </div>
                          <p className="text-sm text-gray-600 line-clamp-3">{ev.passage}</p>
                          <div className="mt-2 flex items-center gap-2 text-xs text-gray-400">
                            <span>Relevance: {(ev.relevance_score * 100).toFixed(0)}%</span>
                            <span>Authority: {(ev.authority_score * 100).toFixed(0)}%</span>
                            <span>Freshness: {(ev.freshness_score * 100).toFixed(0)}%</span>
                          </div>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <svg className="w-16 h-16 mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
              </svg>
              <p className="text-lg font-medium">Select a claim</p>
              <p className="text-sm mt-1">Click on a claim in the answer to view its supporting evidence</p>
            </div>
          )}
        </div>

        {/* Footer with source link */}
        {selectedEvidenceId && evidenceMap.get(selectedEvidenceId) && (
          <div className="p-4 border-t border-gray-200 bg-gray-50/50">
            <a
              href={evidenceMap.get(selectedEvidenceId)!.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm text-accent-700 hover:underline font-medium"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Open full source
            </a>
          </div>
        )}
      </div>
    </div>
  );
}