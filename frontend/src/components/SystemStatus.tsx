import { useEffect, useState } from "react";
import { getProviderStatus } from "../api/client";
import { capitalize } from "../lib/format";
import type { ProviderStatus } from "../types";

interface Props {
  onClose: () => void;
}

const STATE_LABELS: Record<string, { label: string; classes: string }> = {
  closed: { label: "Healthy", classes: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  open: { label: "Open (failing)", classes: "bg-red-50 text-red-700 border-red-200" },
  half_open: { label: "Recovering", classes: "bg-amber-50 text-amber-700 border-amber-200" },
};

export default function SystemStatus({ onClose }: Props) {
  const [providers, setProviders] = useState<ProviderStatus[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const status = await getProviderStatus();
      setProviders(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reach the backend.");
      setProviders(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="System status">
      <div className="absolute inset-0 bg-gray-900/40 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="section-label mb-1">Backend</p>
            <h2 className="text-lg font-semibold text-gray-900">System status</h2>
          </div>
          <button onClick={onClose} className="btn-secondary text-xs py-1.5 px-2.5" aria-label="Close">
            Close
          </button>
        </div>

        {loading && <p className="text-sm text-gray-500">Checking provider status…</p>}

        {error && !loading && (
          <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm p-3">{error}</div>
        )}

        {providers && !loading && (
          <ul className="space-y-2">
            {providers.map((p) => {
              const state = STATE_LABELS[p.circuit_breaker_state ?? "closed"] ?? STATE_LABELS.closed;
              return (
                <li key={p.name} className="flex items-center justify-between rounded-xl border border-gray-200 px-4 py-3">
                  <div>
                    <span className="font-medium text-gray-800 capitalize">{p.name}</span>
                    <div className="text-xs text-gray-400">
                      breaker failures: {p.circuit_breaker_failure_count ?? 0}
                    </div>
                  </div>
                  <span className={`text-[11px] font-medium px-2.5 py-1 rounded-full border ${state.classes}`}>
                    {capitalize(state.label)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}

        <button onClick={() => void load()} className="btn-secondary mt-5 w-full text-sm justify-center" disabled={loading}>
          {loading ? "Refreshing…" : "Refresh status"}
        </button>
      </div>
    </div>
  );
}