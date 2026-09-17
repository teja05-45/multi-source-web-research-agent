import { useState, useRef, useEffect } from "react";
import type { ResearchRequestCreate } from "../types";

interface Props {
  onSubmit: (question: string, maxSources: number, depth: ResearchRequestCreate["depth"]) => void;
  disabled: boolean;
  placeholder?: string;
}

export default function Composer({ onSubmit, disabled, placeholder = "Ask a follow-up question…" }: Props) {
  const [question, setQuestion] = useState("");
  const [maxSources, setMaxSources] = useState(8);
  const [depth, setDepth] = useState<ResearchRequestCreate["depth"]>("standard");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [question]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || disabled) return;
    onSubmit(question.trim(), maxSources, depth);
    setQuestion("");
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }, 0);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="sticky bottom-0 bg-white/95 backdrop-blur-sm border-t border-gray-200">
      <div className="max-w-4xl mx-auto px-6 pb-6 pt-4">
        <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm">
          <label htmlFor="question" className="sr-only">
            Research question
          </label>
          <textarea
            ref={textareaRef}
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            maxLength={1000}
            className="input resize-none px-4 py-3 min-h-[52px] max-h-[200px]"
            disabled={disabled}
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
                    disabled={disabled}
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
                disabled={disabled}
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

        <p className="text-center text-xs text-gray-400 mt-3">
          Press <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-600 border border-gray-200">⌘</kbd> + <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-gray-600 border border-gray-200">Enter</kbd> to send • Shift+Enter for new line
        </p>
      </div>
  </form>
  );
}