import { useState, useEffect, useCallback } from "react";
import { listConversations, updateConversation, deleteConversation } from "../api/client";
import type { Conversation } from "../types";
import { formatDistanceToNow } from "../lib/format";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  activeConversationId?: string;
  onNewResearch: () => void;
}

export default function Sidebar({ isOpen, onClose, activeConversationId, onNewResearch }: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renamingValue, setRenamingValue] = useState("");

  const loadConversations = useCallback(async () => {
    try {
      const list = await listConversations(undefined, search || undefined, 50, 0);
      setConversations(list);
    } catch {
      // silent — non-critical UI failure
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    setLoading(true);
    loadConversations();
  }, [loadConversations]);

  // Refresh when a research run (or any other flow) creates or changes
  // conversations in the current tab, and when the tab regains focus.
  useEffect(() => {
    const refresh = () => loadConversations();
    window.addEventListener("researchlens:conversations-changed", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("researchlens:conversations-changed", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [loadConversations]);

  function startRename(c: Conversation) {
    setRenamingId(c.id);
    setRenamingValue(c.title);
  }

  async function commitRename() {
    if (!renamingId || !renamingValue.trim()) {
      setRenamingId(null);
      return;
    }
    try {
      const updated = await updateConversation(renamingId, { title: renamingValue.trim() });
      setConversations((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    } catch {
      // leave old title
    }
    setRenamingId(null);
  }

  async function handleDelete(id: string) {
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
    } catch {
      // silent
    }
  }

  function handleConversationClick(id: string) {
    window.location.href = `/conversation/${id}`;
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      setRenamingId(null);
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      commitRename();
    }
  }

  return (
    <aside
      className={`
        fixed inset-y-0 left-0 z-40 w-80 bg-white border-r border-gray-200/80
        transform transition-transform duration-200 ease-in-out
        ${isOpen ? "translate-x-0" : "-translate-x-full"}
        lg:translate-x-0
      `}
      aria-label="Conversations"
    >
      <div className="flex flex-col h-full">
        {/* Mobile close button */}
        <div className="lg:hidden flex items-center justify-end p-3 border-b border-gray-200/80">
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            aria-label="Close sidebar"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Header */}
        <div className="p-4 border-b border-gray-200/80 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-500 to-accent-700 flex items-center justify-center text-white text-sm font-bold shadow-sm">
              R
            </div>
            <span className="text-lg font-semibold tracking-tight text-gray-900">ResearchLens</span>
          </div>
          <button
            onClick={onClose}
            className="lg:hidden p-2 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            aria-label="Close sidebar"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* New Research button */}
        <div className="p-3 border-b border-gray-200/80">
          <button
            onClick={() => {
              onNewResearch();
              onClose();
            }}
            className="btn-primary w-full text-sm"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New research
          </button>
        </div>

        {/* Search */}
        <div className="px-3 pt-3 pb-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search conversations…"
            className="input-field text-sm"
          />
        </div>

        {/* Conversation list */}
        <nav className="flex-1 overflow-y-auto" aria-label="Conversation history">
          {loading ? (
            <div className="p-6 text-center text-sm text-gray-400">Loading…</div>
          ) : conversations.length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-400">
              {search ? "No matches" : "No conversations yet"}
            </div>
          ) : (
            <ul className="p-2 space-y-0.5">
              {conversations.map((c) => {
                const isActive = c.id === activeConversationId;
                return (
                  <li key={c.id}>
                    {renamingId === c.id ? (
                      <input
                        type="text"
                        value={renamingValue}
                        onChange={(e) => setRenamingValue(e.target.value)}
                        onBlur={commitRename}
                        onKeyDown={handleKeyDown}
                        autoFocus
                        className="input-field text-sm w-full"
                      />
                    ) : (
                      <button
                        onClick={() => handleConversationClick(c.id)}
                        onDoubleClick={() => startRename(c)}
                        className={`
                          w-full text-left px-3 py-2.5 rounded-lg transition-colors
                          ${isActive
                            ? "bg-accent-50 text-accent-800 font-medium"
                            : "text-gray-700 hover:bg-gray-100"
                          }
                        `}
                        title={c.title}
                      >
                        <div className="text-sm truncate">{c.title}</div>
                        <div className="flex items-center justify-between mt-1 text-xs text-gray-400">
                          <span>{formatDistanceToNow(new Date(c.updated_at), { addSuffix: true })}</span>
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={(e) => { e.stopPropagation(); startRename(c); }}
                              className="p-0.5 rounded hover:text-gray-700 transition-colors"
                              title="Rename"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                              </svg>
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDelete(c.id); }}
                              className="p-0.5 rounded hover:text-red-600 transition-colors"
                              title="Delete"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </nav>

        {/* Footer */}
        <div className="border-t border-gray-200/80 px-4 py-3 text-xs text-gray-400 text-center">
          Evidence-grounded research
        </div>
      </div>
    </aside>
  );
}
