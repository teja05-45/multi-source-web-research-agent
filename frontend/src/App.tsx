import { useState } from "react";
import AnswerView from "./components/AnswerView";
import ConflictsView from "./components/ConflictsView";
import Header from "./components/Header";
import ProgressStages from "./components/ProgressStages";
import QueryInput from "./components/QueryInput";
import ResearchTraceView from "./components/ResearchTrace";
import SourcesList from "./components/SourcesList";
import SystemStatus from "./components/SystemStatus";
import { ApiError, runResearch } from "./api/client";
import type { ResearchReport, ResearchRequest } from "./types";

type Status = "idle" | "loading" | "success" | "error";

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

export default function App() {
  const [status, setStatus] = useState<Status>("idle");
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progressIndex, setProgressIndex] = useState(0);
  const [showStatus, setShowStatus] = useState(false);
  const [activeQuestion, setActiveQuestion] = useState("");

  async function handleSubmit(question: string, maxSources: number, depth: ResearchRequest["depth"]) {
    setStatus("loading");
    setError(null);
    setReport(null);
    setActiveQuestion(question);
    setProgressIndex(0);

    const interval = setInterval(() => {
      setProgressIndex((i) => Math.min(i + 1, 6));
    }, 900);

    try {
      const result = await runResearch({ question, max_sources: maxSources, depth });
      setReport(result);
      setStatus("success");
      setProgressIndex(7);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Something went wrong while researching this question.";
      setError(message);
      setStatus("error");
    } finally {
      clearInterval(interval);
    }
  }

  function reset() {
    setStatus("idle");
    setReport(null);
    setError(null);
    setActiveQuestion("");
  }

  return (
    <div id="top" className="min-h-screen bg-[#fafafa]">
      <Header onShowSystemStatus={() => setShowStatus(true)} />

      <main>
        {status !== "success" && (
          <QueryInput onSubmit={handleSubmit} disabled={status === "loading"} />
        )}

        {status === "loading" && (
          <div className="max-w-3xl mx-auto px-6 pb-10 -mt-4">
            <div className="card p-6">
              <div className="text-sm text-gray-500 mb-4">Researching</div>
              <div className="text-gray-900 font-medium leading-snug">{activeQuestion}</div>
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

        {status === "success" && report && (
          <div className="max-w-6xl mx-auto px-6 pb-16 pt-2 space-y-6">
            <div className="card p-6">
              <div className="flex flex-wrap items-center gap-3">
                <span className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                  Report ready
                </span>
                <div className="min-w-0">
                  <div className="text-xs text-gray-400">Question</div>
                  <div className="text-gray-900 font-medium">{report.question}</div>
                </div>
                <div className="flex-1" />
                <button onClick={reset} className="btn-secondary text-sm">
                  New research
                </button>
              </div>
            </div>

            <AnswerView
              answer={report.answer}
              keyClaims={report.key_claims}
              trace={report.research_trace}
              degraded={report.degraded}
            />
            <ConflictsView conflicts={report.conflicts} uncertainties={report.uncertainties} />
            <SourcesList sources={report.sources} />
            <ResearchTraceView trace={report.research_trace} />
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

      <footer className="border-t border-gray-200 bg-white/60">
        <div className="max-w-6xl mx-auto px-6 py-6 text-center text-xs text-gray-400">
          Multi-Source Web Research Agent — evidence-grounded research powered by independent search providers.
        </div>
      </footer>

      {showStatus && <SystemStatus onClose={() => setShowStatus(false)} />}
    </div>
  );
}