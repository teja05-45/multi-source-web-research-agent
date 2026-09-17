import { capitalize } from "../lib/format";
import type { Conflict, Uncertainty } from "../types";

interface Props {
  conflicts: Conflict[];
  uncertainties: Uncertainty[];
}

export default function ConflictsView({ conflicts, uncertainties }: Props) {
  if (conflicts.length === 0 && uncertainties.length === 0) return null;

  return (
    <div className="card p-6 sm:p-8 space-y-8">
      {conflicts.length > 0 && (
        <section>
          <div className="flex items-baseline justify-between mb-4">
            <p className="section-label">Conflicts</p>
            <span className="text-sm text-amber-600 font-medium">{conflicts.length}</span>
          </div>
          <ul className="space-y-3">
            {conflicts.map((c, i) => (
              <li key={i} className="rounded-xl border border-amber-200 bg-amber-50/70 p-4 text-sm">
                <div className="font-medium text-amber-800 mb-2">
                  Disagreement about: {capitalize(c.topic)}
                </div>
                <div className="text-gray-700">
                  <span className="font-medium">{c.position_a_sources.join(", ")}:</span>{" "}
                  {c.position_a}
                </div>
                <div className="text-gray-700 mt-1">
                  <span className="font-medium">{c.position_b_sources.join(", ")}:</span>{" "}
                  {c.position_b}
                </div>
                {c.possible_explanation && (
                  <div className="mt-2 text-xs text-gray-500">
                    Possible explanation: {c.possible_explanation}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {uncertainties.length > 0 && (
        <section>
          <p className="section-label mb-4">Uncertainty</p>
          <ul className="space-y-2 text-sm text-gray-700">
            {uncertainties.map((u, i) => (
              <li key={i} className="flex items-start gap-2.5">
                <span className="shrink-0 text-[11px] font-medium px-2 py-0.5 rounded-full bg-gray-100 border border-gray-200 text-gray-600">
                  {u.reason.replace(/_/g, " ")}
                </span>
                <span>{u.description}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}