import React from "react";
import { BrowserRouter, Routes, Route, Navigate, Link } from "react-router-dom";
import { Toaster } from "react-hot-toast";

import PostureStudio from "./pages/PostureStudio";
import WorkoutEngine from "./pages/WorkoutEngine";
import CoachChat from "./pages/CoachChat";
import ProgressAnalytics from "./pages/ProgressAnalytics";
import { AuthProvider } from "./hooks/useAuth"; // <-- Oturum yöneticisini içeri aktarıyoruz

function DashboardLayout() {
  return (
    <div className="flex min-h-screen bg-base text-text-primary">
      {/* Sol Menü (Sidebar) */}
      <aside className="w-64 border-r border-border bg-surface p-4 flex flex-col justify-between shrink-0 h-screen sticky top-0">
        <div className="space-y-6">
          <div className="px-4 py-2">
            <h1 className="font-display text-xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">AuraFit AI</h1>
            <p className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">Graduation Project</p>
          </div>
          <nav className="space-y-1">
            <Link to="/posture" className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-card transition-colors">
              📸 Posture Studio
            </Link>
            <Link to="/workout" className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-card transition-colors">
              🏋️ AI Workout Engine
            </Link>
            <Link to="/coach" className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-card transition-colors">
              💬 FitCoach Chat
            </Link>
            <Link to="/progress" className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-card transition-colors">
              📊 Progress Analytics
            </Link>
          </nav>
        </div>
        <div className="p-3 border-t border-border flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          <span className="text-[11px] text-text-muted">System Synchronized</span>
        </div>
      </aside>

      {/* Sağ taraftaki dinamik içerik alanı */}
      <div className="flex-1 min-w-0 flex flex-col">
        <Routes>
          <Route path="posture" element={<PostureStudio />} />
          <Route path="workout" element={<WorkoutEngine />} />
          <Route path="coach" element={<CoachChat />} />
          <Route path="progress" element={<ProgressAnalytics />} />
          <Route path="" element={<Navigate to="posture" replace />} />
        </Routes>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      {/* Tüm projeyi AuthProvider ile sarmalayarak kullanıcı bilgisini sayfalara dağıtıyoruz */}
      <AuthProvider>
        <Toaster position="top-right" />
        <Routes>
          <Route path="/*" element={<DashboardLayout />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}