import { useParams } from "react-router-dom";
import ChatView from "./ChatView";

export function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>();

  if (!conversationId) return null;

  return (
    <ChatView
      conversationId={conversationId}
      onBack={() => { window.location.href = "/"; }}
    />
  );
}
