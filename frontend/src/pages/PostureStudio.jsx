import React, { useState } from "react";
import { ScanFace, Upload, CheckCircle } from "lucide-react";
import toast from "react-hot-toast";

export default function PostureStudio() {
  const [loading, setLoading] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);

  const handleAnalyze = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      setAnalyzed(true);
      toast.success("Analysis complete!");
    }, 2000);
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h2 className="font-display text-2xl font-bold">Posture Analysis Studio</h2>
        <p className="text-sm text-text-secondary">Upload your photos for a full-body posture scan powered by MediaPipe</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="card p-6 flex flex-col items-center justify-center border-dashed border-2 min-h-[250px]">
          <Upload size={32} className="text-text-muted mb-2" />
          <p className="text-sm text-text-secondary text-center">Drag & drop or click to upload full-body photos</p>
          <p className="text-xs text-text-muted mt-1">Front, Back, or Side profiles</p>
        </div>

        <div className="card p-6 space-y-4 flex flex-col justify-between">
          <div>
            <h3 className="font-semibold text-lg mb-2">Analysis Engine Controls</h3>
            <p className="text-xs text-text-secondary leading-relaxed">
              Once photos are staged, the vision engine computes skeletal landmarks to detect metrics like shoulder tilt or spine lateral deviation.
            </p>
          </div>
          <button onClick={handleAnalyze} disabled={loading} className="btn-primary w-full justify-center">
            {loading ? "Processing Landmarks..." : <><ScanFace size={16} /> Run Vision Diagnostics</>}
          </button>
        </div>
      </div>

      {analyzed && (
        <div className="card-glow p-6 space-y-3 animate-fade-in">
          <div className="flex items-center gap-2 text-accent">
            <CheckCircle size={18} />
            <span className="font-medium">Skeletal Landmarks Successfully Parsed</span>
          </div>
          <p className="text-sm text-text-secondary">
            Mock Score: <span className="text-accent font-bold">84 / 100</span> (Excellent alignment detected. Slight adjustments suggested for head forward displacement metrics).
          </p>
        </div>
      )}
    </div>
  );
}