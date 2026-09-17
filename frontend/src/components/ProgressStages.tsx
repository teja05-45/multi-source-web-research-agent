const STAGES = [
  "Planning",
  "Searching",
  "Normalizing",
  "Deduplicating",
  "Ranking",
  "Fetching",
  "Verifying",
  "Synthesizing",
];

interface Props {
  activeIndex: number;
}

export default function ProgressStages({ activeIndex }: Props) {
  return (
    <div className="card p-6 max-w-3xl mx-auto" role="status" aria-live="polite" aria-label="Research in progress">
      <ol className="flex flex-wrap gap-2.5 justify-center">
        {STAGES.map((stage, i) => {
          const isDone = i < activeIndex;
          const isActive = i === activeIndex;
          return (
            <li
              key={stage}
              className={`text-sm px-3.5 py-1.5 rounded-full border transition-colors ${
                isDone
                  ? "bg-accent-50 border-accent-200 text-accent-700"
                  : isActive
                  ? "bg-accent-600 border-accent-600 text-white"
                  : "bg-gray-50 border-gray-200 text-gray-400"
              }`}
            >
              {stage}
              {isActive && (
                <span aria-hidden="true" className="inline-block w-1.5 h-1.5 ml-2 rounded-full bg-white/80 animate-pulse align-middle" />
              )}
            </li>
          );
        })}
      </ol>
      <p className="text-center text-xs text-gray-400 mt-4">Running the research pipeline across providers…</p>
    </div>
  );
}