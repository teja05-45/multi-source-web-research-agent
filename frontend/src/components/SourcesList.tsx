import type { SourceSummary } from "../types";

interface Props {
  sources: SourceSummary[];
}

function domainInitial(domain: string): string {
  return (domain.replace(/^www\./, "")[0] || "?").toUpperCase();
}

export default function SourcesList({ sources }: Props) {
  if (sources.length === 0) {
    return (
      <div className="card p-6">
        <p className="section-label mb-2">Sources</p>
        <p className="text-sm text-gray-500">No sources were retrieved for this request.</p>
      </div>
    );
  }

  return (
    <div className="card p-6 sm:p-8">
      <div className="flex items-baseline justify-between mb-5">
        <p className="section-label">Sources</p>
        <span className="text-sm text-gray-400">{sources.length}</span>
      </div>
      <ul className="grid gap-3 md:grid-cols-2">
        {sources.map((source) => (
          <li
            key={source.source_id}
            className="rounded-xl border border-gray-200 p-4 hover:border-accent-200 hover:shadow-sm transition-all"
          >
            <div className="flex items-start gap-3">
              <div
                aria-hidden="true"
                className="shrink-0 w-9 h-9 rounded-lg bg-gradient-to-br from-accent-500 to-accent-700 text-white text-sm font-semibold flex items-center justify-center"
              >
                {domainInitial(source.domain)}
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
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-2 text-xs text-gray-500">
                  <span className="text-gray-400">{source.domain}</span>
                  <span aria-hidden="true">·</span>
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
    </div>
  );
}