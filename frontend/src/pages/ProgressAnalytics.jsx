import React from "react";
import { BarChart3, TrendingUp, Award, Activity } from "lucide-react";

export default function ProgressAnalytics() {
  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h2 className="font-display text-2xl font-bold">Progress Analytics</h2>
        <p className="text-sm text-text-secondary">Compare baseline posture metrics across months to track alignment improvements</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="stat-card">
          <TrendingUp className="text-primary" size={20} />
          <p className="text-xs text-text-secondary uppercase mt-1">Baseline Score</p>
          <p className="text-2xl font-bold font-display">74.0</p>
        </div>
        <div className="stat-card">
          <Activity className="text-accent" size={20} />
          <p className="text-xs text-text-secondary uppercase mt-1">Current Score</p>
          <p className="text-2xl font-bold font-display">84.0</p>
        </div>
        <div className="stat-card">
          <Award className="text-warning" size={20} />
          <p className="text-xs text-text-secondary uppercase mt-1">Net Delta Delta</p>
          <p className="text-2xl font-bold font-display text-accent">+10.0</p>
        </div>
      </div>

      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="text-primary" size={18} />
          <h3 className="font-semibold text-base">Analytical Metrics Matrix</h3>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">
          The alignment delta calculations indicate that structural shifts in shoulder stability and overall balance are moving in an optimal vector. Recharts visualization interfaces will dynamically bind here once production database synchronization logs are established.
        </p>
      </div>
    </div>
  );
}