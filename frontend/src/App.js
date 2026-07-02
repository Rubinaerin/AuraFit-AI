import React from "react";
import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";

// Sadece senin pages/ klasöründe fiziksel olarak bulunan 4 sayfayı import ediyoruz
import PostureStudio from "./pages/PostureStudio";
import WorkoutEngine from "./pages/WorkoutEngine";
import CoachChat from "./pages/CoachChat";
import ProgressAnalytics from "./pages/ProgressAnalytics";

// Eksik olan layout bileşenleri yerine basit bir geçici test menüsü (Sidebar) oluşturuyoruz
function TemporaryLayout({ children }) {
  return (
    <div className="flex min-h-screen bg-base text-text-primary">
      {/* Sol Menü (Sidebar) */}
      <aside className="w-64 border-r border-border bg-surface p-4 space-y-4">
        <div className="px-4 py-2">
          <h1 className="font-display text-xl font-bold text-gradient-primary">AuraFit AI</h1>
          <p className="text-[10px] text-text-muted uppercase tracking-wider">Graduation Project</p>
        </div>
        <nav className="space-y-1">
          <Link to="/posture" className="block px-4 py-2.5 rounded-xl hover:bg-card text-sm font-medium transition-colors">📸 Posture Studio</Link>
          <Link to="/workout" className="block px-4 py-2.5 rounded-xl hover:bg-card text-sm font-medium transition-colors">🏋️ AI Workout Engine</Link>
          <Link to="/coach" className="block px-4 py-2.5 rounded-xl hover:bg-card text-sm font-medium transition-colors">💬 FitCoach Chat</Link>
          <Link to="/progress" className="block px-4 py-2.5 rounded-xl hover:bg-card text-sm font-medium transition-colors">📊 Progress Analytics</Link>
        </nav>
      </aside>
      {/* Sağ İçerik Alanı */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" />
      <Routes>
        <Route path="/posture" element={<TemporaryLayout><PostureStudio /></TemporaryLayout>} />
        <Route path="/workout" element={<TemporaryLayout><WorkoutEngine /></TemporaryLayout>} />
        <Route path="/coach" element={<TemporaryLayout><CoachChat /></TemporaryLayout>} />
        <Route path="/progress" element={<TemporaryLayout><ProgressAnalytics /></TemporaryLayout>} />
        {/* Ana sayfaya gelindiğinde otomatik olarak Posture Studio'ya yönlendirsin */}
        <Route path="*" element={<Navigate to="/posture" replace />} />
      </Routes>
    </BrowserRouter>
  );
}