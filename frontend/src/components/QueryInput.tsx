import { useState } from "react";
import type { ResearchRequest } from "../types";

interface Props {
  onSubmit: (question: string, maxSources: number, depth: ResearchRequest["depth"]) => void;
  disabled: boolean;
}

const PRESETS = [
  "Compare the current approaches to AI agent memory and explain the major trade-offs.",
  "What is the latest stable version of Python and what changed recently?",
  "How many employees does the company have, according to available reports?",
];

export default function QueryInput({ onSubmit, disabled }: Props) {
  const [question, setQuestion] = useState("");
  const [maxSources, setMaxSources] = useState(8);
  const [depth, setDepth] = useState<ResearchRequest["depth"]>("standard");

  function submit() {
    if (!question.trim() || disabled) return;
    onSubmit(question.trim(), maxSources, depth);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    submit();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      submit();
    }
  }

  return (
    <section className="relative">
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-accent-50/80 via-white to-transparent" aria-hidden="true" />
      <div className="max-w-4xl mx-auto px-6 pt-16 pb-10 text-center">
        <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight text-gray-900">
          Research anything.
          <span className="block text-transparent bg-clip-text bg-gradient-to-r from-accent-600 to-accent-400">
            Verify everything.
          </span>
        </h1>
        <p className="mt-4 text-gray-500 text-lg max-w-2xl mx-auto">
          Every answer is grounded in retrievable evidence from multiple independent
          sources, with citations verified before you see them.
        </p>

        <div className="mt-6 flex flex-wrap justify-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-gray-200 bg-white text-gray-600">
            <span aria-hidden="true">Exactly two providers minimum</span>
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-gray-200 bg-white text-gray-600">
            Per-claim citation validation
          </span>
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-gray-200 bg-white text-gray-600">
            Cross-source conflict detection
          </span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="max-w-3xl mx-auto px-6 pb-8">
        <div className="card p-5 shadow-lg shadow-gray-200/60">
          <label htmlFor="question" className="sr-only">
            Research question
          </label>
          <textarea
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question you want answered from multiple sources…"
            rows={3}
            maxLength={1000}
            className="input resize-none px-4 py-3"
          />

          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex items-center gap-2">
              <label htmlFor="depth" className="text-sm text-gray-600">
                Depth
              </label>
              <div className="inline-flex rounded-lg border border-gray-300 p-0.5" role="group" aria-label="Research depth">
                {(["quick", "standard"] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setDepth(option)}
                    aria-pressed={depth === option}
                    className={`px-3 py-1 text-sm rounded-md transition-colors ${
                      depth === option
                        ? "bg-accent-600 text-white"
                        : "text-gray-600 hover:text-gray-900"
                    }`}
                  >
                    {option === "quick" ? "Quick" : "Standard"}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <label htmlFor="max-sources" className="text-sm text-gray-600">
                Max sources
              </label>
              <select
                id="max-sources"
                value={maxSources}
                onChange={(e) => setMaxSources(Number(e.target.value))}
                className="border border-gray-300 rounded-lg px-2.5 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-accent-500"
              >
                {[4, 6, 8, 10, 12].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex-1" />

            <button type="submit" disabled={disabled || !question.trim()} className="btn-primary">
              {disabled ? (
                <>
                  <span aria-hidden="true" className="w-3 h-3 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                  Researching…
                </>
              ) : (
                "Research"
              )}
            </button>
          </div>
        </div>

        <div className="mt-4 text-center">
          <p className="text-xs text-gray-400 mb-2">Try an example</p>
          <div className="flex flex-wrap justify-center gap-2">
            {PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                disabled={disabled}
                onClick={() => {
                  setQuestion(preset);
                  setDepth("standard");
                }}
                className="max-w-xs truncate text-left text-xs px-3 py-1.5 rounded-full border border-gray-200 bg-white text-gray-500 hover:border-accent-300 hover:text-accent-700 transition-colors disabled:opacity-50"
                title={preset}
              >
                {preset.length > 60 ? `${preset.slice(0, 60)}…` : preset}
              </button>
            ))}
          </div>
        </div>
      </form>
    </section>
  );
}