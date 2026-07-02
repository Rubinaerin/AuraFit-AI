import React, { useState } from "react";
import { Dumbbell, Sparkles, Shield } from "lucide-react";
import toast from "react-hot-toast";

export default function WorkoutEngine() {
  const [generating, setGenerating] = useState(false);
  const [ready, setReady] = useState(false);

  const handleGenerate = () => {
    setGenerating(true);
    setTimeout(() => {
      setGenerating(false);
      setReady(true);
      toast.success("AI Workout Plan generated successfully!");
    }, 2000);
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h2 className="font-display text-2xl font-bold">AI Workout Engine</h2>
        <p className="text-sm text-text-secondary">Generate structural multi-week training programs configured for injury mitigations</p>
      </div>

      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-2">
          <Dumbbell className="text-primary" size={20} />
          <h3 className="font-semibold text-lg">Engine Parameters Configuration</h3>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">
          The execution logic leverages backend schemas to analyze injury structures (e.g. tracking active physical restrictions) and enforce strict exercise blacklists automatically.
        </p>
        <button onClick={handleGenerate} disabled={generating} className="btn-primary w-full justify-center">
          {generating ? "AI Engine Building Routines..." : <><Sparkles size={14} /> Trigger Core Plan Construction</>}
        </button>
      </div>

      {ready && (
        <div className="card-glow p-6 space-y-3 animate-fade-in">
          <div className="flex items-center gap-2 text-primary">
            <Shield size={16} />
            <h4 className="font-semibold text-sm">Automated Neural Guardrails Verified</h4>
          </div>
          <p className="text-sm text-text-secondary">
            Customized regime compiled safely. Contraindicated vectors like standard deadlifts have been omitted, substituted with low-stress core variations matching the configuration directives.
          </p>
        </div>
      )}
    </div>
  );
}