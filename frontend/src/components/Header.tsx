interface Props {
  onShowSystemStatus: () => void;
}

export default function Header({ onShowSystemStatus }: Props) {
  return (
    <header className="border-b border-gray-200/80 bg-white/85 backdrop-blur sticky top-0 z-20">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <a href="#top" className="flex items-center gap-2.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 rounded-lg">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-500 to-accent-700 flex items-center justify-center text-white text-sm font-bold shadow-sm">
            R
          </div>
          <span className="text-lg font-semibold tracking-tight text-gray-900">ResearchLens</span>
        </a>
        <nav className="hidden sm:flex items-center gap-7 text-sm text-gray-600">
          <a href="#how-it-works" className="hover:text-gray-900 transition-colors">
            How it works
          </a>
          <button
            onClick={onShowSystemStatus}
            className="inline-flex items-center gap-2 text-gray-700 hover:text-gray-900 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 rounded-lg px-1.5 py-0.5"
          >
            <span aria-hidden="true" className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>System status</span>
          </button>
        </nav>
      </div>
    </header>
  );
}