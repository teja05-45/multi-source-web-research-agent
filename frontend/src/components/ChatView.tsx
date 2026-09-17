import { useState, useEffect, useCallback, useRef } from "react";
import { runResearchInConversation, getConversation, listMessages } from "../api/client";
import type { Conversation, Message } from "../types";
import MessageComponent from "./Message";
import Composer from "./Composer";
import { formatDistanceToNow } from "date-fns";

interface Props {
  conversationId: string;
  onBack: () => void;
}

export function ChatView({ conversationId, onBack }: Props) {

  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [conv, msgs] = await Promise.all([
        getConversation(conversationId),
        listMessages(conversationId, 100, 0),
      ]);
      setConversation(conv);
      setMessages(msgs);
    } catch (err) {
      console.error("Failed to load conversation:", err);
      setError("Failed to load conversation");
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSubmit = useCallback(async (question: string, maxSources: number, depth: "quick" | "standard" | undefined) => {
    if (!question.trim() || sending) return;

    setSending(true);
    setError(null);

    try {
      const tempUserMessage: Message = {
        id: `temp-${Date.now()}`,
        conversation_id: conversationId,
        role: "user",
        content: question,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, tempUserMessage]);

      await runResearchInConversation(conversationId, {
        question,
        max_sources: maxSources,
        depth: depth ?? "standard",
      });

      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setSending(false);
    }
  }, [conversationId, loadData]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-accent-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-500">Loading conversation…</p>
        </div>
      </div>
    );
  }

  if (!conversation) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-500">Conversation not found</p>
          <button onClick={onBack} className="btn-secondary mt-4">Back to conversations</button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <header className="border-b border-gray-200 bg-white/80 backdrop-blur sticky top-0 z-20 px-6 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <button onClick={onBack} className="btn-secondary text-sm mr-4" disabled={sending}>
            ← Back
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold text-gray-900 truncate">{conversation.title}</h1>
            <p className="text-xs text-gray-500 truncate">
              {conversation.message_count} messages • {formatDistanceToNow(new Date(conversation.updated_at), { addSuffix: true })}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
              conversation.status === "active"
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-gray-100 text-gray-600 border-gray-200"
            }`}>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="capitalize">{conversation.status}</span>
            </span>
            <button onClick={onBack} className="btn-secondary text-sm">
              Conversations
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-6 max-w-4xl mx-auto w-full">
        <div className="space-y-6" role="log" aria-live="polite" aria-label="Conversation">
          {messages.map((message, _index) => (
            <MessageComponent
              key={message.id}
              message={message}
            />
          ))}

          {sending && (
            <div className="flex justify-start">
              <div className="max-w-[85%]">
                <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-5 py-4 animate-pulse">
                  <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
                  <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </main>

      <Composer
        onSubmit={handleSubmit}
        disabled={sending}
        placeholder="Ask a follow-up question…"
      />

      {error && (
        <div className="fixed bottom-4 right-4 z-50">
          <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 p-4 shadow-lg max-w-md">
            <p className="font-medium">Error</p>
            <p className="text-sm mt-1">{error}</p>
            <button onClick={() => setError(null)} className="text-sm text-red-600 hover:underline mt-2">Dismiss</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ChatView;