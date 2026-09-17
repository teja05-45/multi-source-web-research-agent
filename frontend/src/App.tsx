import { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import SystemStatus from "./components/SystemStatus";
import { LandingPage } from "./components/LandingPage";
import { ConversationPage } from "./components/ConversationPage";

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showStatus, setShowStatus] = useState(false);

  return (
    <BrowserRouter>
      <div id="top" className="min-h-screen bg-[#fafafa]">
        {/* Mobile sidebar toggle */}
        <button
          className="lg:hidden fixed top-4 left-4 z-50 btn-primary shadow-lg"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open sidebar"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <Sidebar
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNewResearch={() => window.location.href = "/"}
        />

        <div className="lg:pl-80 min-h-screen flex flex-col">
          <Header onShowSystemStatus={() => setShowStatus(true)} />

          <main className="flex-1">
            <Routes>
              {/* Landing page - new research */}
              <Route
                path="/"
                element={<LandingPage />}
              />

              {/* Conversation view */}
              <Route
                path="/conversation/:conversationId"
                element={<ConversationPage />}
              />

              {/* Redirect unknown routes */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>

          <footer className="border-t border-gray-200 bg-white/60">
            <div className="max-w-6xl mx-auto px-6 py-6 text-center text-xs text-gray-400">
              ResearchLens — Evidence-grounded research powered by independent search providers.
            </div>
          </footer>
        </div>

        {showStatus && <SystemStatus onClose={() => setShowStatus(false)} />}
      </div>
    </BrowserRouter>
  );
}