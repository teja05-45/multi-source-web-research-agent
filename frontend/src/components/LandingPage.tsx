import { useState } from "react";
import ProgressStages from "./ProgressStages";
import QueryInput from "./QueryInput";
import { createConversation, runResearchInConversation } from "../api/client";

const PIPELINE_STEPS = [
  {
    title: "Search",
    body: "Each question is posed to multiple independent search providers in parallel.",
  },
  {
    title: "Deduplicate & rank",
    body: "Near-duplicate results are merged and relevance-scored against the question.",
  },
  {
    title: "Fetch & extract",
    body: "Top-ranked pages are fetched and the most query-relevant passages extracted.",
  },
  {
    title: "Verify & cite",
    body: "Each claim is checked against evidence; unsupported claims are flagged, citations validated.",
  },
];

export function LandingPage() {
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [progressIndex, setProgressIndex] = useState(0);

  async function handleSubmit(question: string, maxSources: number, depth: "quick" | "standard" | undefined) {
    setStatus("loading");
    setError(null);
    setProgressIndex(0);

    const interval = setInterval(() => {
      setProgressIndex((i) => Math.min(i + 1, 6));
    }, 900);

    try {
      const conversation = await createConversation({ title: question.slice(0, 80) });
      
      await runResearchInConversation(conversation.id, {
        question,
        max_sources: maxSources,
        depth: depth ?? "standard",
      });
      
      setStatus("success");
      setProgressIndex(7);
      
      window.location.href = `/conversation/${conversation.id}`;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong while researching this question.";
      setError(message);
      setStatus("error");
      window.dispatchEvent(new Event("researchlens:conversations-changed"));
    } finally {
      clearInterval(interval);
    }
  }

  function reset() {
    setStatus("idle");
    setError(null);
  }

  return (
    <div className="min-h-screen bg-[#fafafa]">
      <main>
        {status !== "success" && (
          <QueryInput onSubmit={handleSubmit} disabled={status === "loading"} />
        )}

        {status === "loading" && (
          <div className="max-w-3xl mx-auto px-6 pb-10 -mt-4">
            <div className="card p-6">
              <div className="text-sm text-gray-500 mb-4">Researching</div>
              <div className="text-gray-900 font-medium leading-snug">{/* question will be shown */}</div>
            </div>
            <div className="mt-4">
              <ProgressStages activeIndex={progressIndex} />
            </div>
          </div>
        )}

        {status === "error" && (
          <div className="max-w-3xl mx-auto px-6 pb-12 -mt-4 space-y-4">
            <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700">
              <p className="font-medium">Research failed</p>
              <p className="text-sm mt-1">{error}</p>
            </div>
            <div className="flex justify-center">
              <button onClick={reset} className="btn-secondary text-sm">
                Try again
              </button>
            </div>
          </div>
        )}

        {status === "idle" && (
          <section id="how-it-works" className="max-w-5xl mx-auto px-6 pb-16 pt-6 scroll-mt-20">
            <p className="section-label text-center mb-8">How it works</p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {PIPELINE_STEPS.map((step, i) => (
                <div key={step.title} className="card p-5">
                  <div className="text-xs font-semibold text-accent-600 mb-2">Step {i + 1}</div>
                  <h3 className="font-semibold text-gray-900">{step.title}</h3>
                  <p className="mt-1.5 text-sm text-gray-500 leading-relaxed">{step.body}</p>
                </div>
              ))}
            </div>
            <p className="mt-8 text-center text-sm text-gray-400 max-w-xl mx-auto">
              This is a deliberately deterministic pipeline: conflict detection and citation
              validation run over real retrieved evidence, so nothing on this page is generated
              without a verifiable basis.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}