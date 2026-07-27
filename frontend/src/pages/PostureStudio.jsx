import React, { useState, useEffect, useCallback } from "react";
import { useOutletContext } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import {
  ScanFace, Upload, X, CheckCircle, AlertTriangle,
  ChevronRight, Info, RotateCcw,
} from "lucide-react";
import toast from "react-hot-toast";
import Topbar from "../components/layout/Topbar";
import ScoreRing from "../components/ui/ScoreRing";
import Spinner from "../components/ui/Spinner";
import { postureService } from "../services/postureService";

const ANGLES = [
  { key: "front", label: "Front View", hint: "Face the camera, arms at sides" },
  { key: "back",  label: "Back View",  hint: "Turn 180°, look straight ahead" },
  { key: "left",  label: "Left Side",  hint: "Left shoulder toward camera" },
  { key: "right", label: "Right Side", hint: "Right shoulder toward camera" },
];

const METRIC_LABELS = {
  shoulder_tilt_deg:     { label: "Shoulder Tilt",       unit: "°", invert: true },
  hip_tilt_deg:          { label: "Hip Tilt",            unit: "°", invert: true },
  spine_lateral_dev_deg: { label: "Spine Lateral Dev.",  unit: "°", invert: true },
  head_forward_deg:      { label: "Head Forward",        unit: "°", invert: true },
  torso_lean_deg:        { label: "Torso Lean",          unit: "°", invert: true },
  shoulder_width_ratio:  { label: "Shoulder/Hip Ratio",  unit: "",  invert: false },
};

function AngleSlot({ angle, file, onDrop, onClear, result, loading }) {
  const onDropCb = useCallback((accepted) => {
    if (accepted[0]) onDrop(angle.key, accepted[0]);
  }, [angle.key, onDrop]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: onDropCb,
    accept: { "image/jpeg": [], "image/png": [], "image/webp": [] },
    multiple: false,
  });

  const preview = file ? URL.createObjectURL(file) : null;

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-text-primary">{angle.label}</p>
          <p className="text-xs text-text-muted">{angle.hint}</p>
        </div>
        {result && (
          <ScoreRing score={result.posture_score} size={52} strokeWidth={5} />
        )}
      </div>

      {!file ? (
        <div
          {...getRootProps()}
          className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-xl p-6 cursor-pointer transition-colors ${
            isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-primary/5"
          }`}
        >
          <input {...getInputProps()} />
          <Upload size={22} className="text-text-muted" />
          <p className="text-xs text-text-secondary text-center">
            {isDragActive ? "Drop here" : "Click or drag photo"}
          </p>
        </div>
      ) : (
        <div className="relative rounded-xl overflow-hidden bg-surface">
          <img
            src={preview}
            alt={angle.label}
            className="w-full h-36 object-cover"
          />
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center bg-base/60">
              <Spinner size={22} />
            </div>
          )}
          <button
            onClick={() => onClear(angle.key)}
            className="absolute top-2 right-2 w-6 h-6 rounded-full bg-base/80 flex items-center justify-center text-text-secondary hover:text-danger"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Per-angle metrics */}
      {result && (
        <div className="space-y-1.5 pt-1">
          {Object.entries(result.metrics || {}).map(([key, val]) => {
            if (val == null) return null;
            const meta = METRIC_LABELS[key];
            if (!meta) return null;
            const abs = Math.abs(val);
            const good = meta.invert ? abs < 5 : val > 0.9;
            return (
              <div key={key} className="flex items-center justify-between text-xs">
                <span className="text-text-secondary">{meta.label}</span>
                <span className={`font-medium ${good ? "text-accent" : abs > 10 ? "text-danger" : "text-warning"}`}>
                  {val.toFixed(1)}{meta.unit}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Warnings */}
      {result?.warnings?.map((w, i) => (
        <div key={i} className="flex items-start gap-2 p-2 rounded-lg bg-warning/5 border border-warning/20">
          <AlertTriangle size={12} className="text-warning mt-0.5 shrink-0" />
          <p className="text-[11px] text-text-secondary leading-relaxed">{w}</p>
        </div>
      ))}
    </div>
  );
}

export default function PostureStudio() {
  const { onMenuClick } = useOutletContext() || {};
  const [photos, setPhotos] = useState({});
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState({});
  const [overallScore, setOverallScore] = useState(null);

  // Load saved analysis results from localStorage on component mount
  useEffect(() => {
    const saved = localStorage.getItem("latest_posture_results");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.results) setResults(parsed.results);
        if (parsed.overallScore != null) setOverallScore(parsed.overallScore);
      } catch (e) {
        console.error("Failed to restore posture data", e);
      }
    }
  }, []);

  const handleDrop = (angle, file) => {
    setPhotos((p) => ({ ...p, [angle]: file }));
    setResults((r) => ({ ...r, [angle]: null }));
  };

  const handleClear = (angle) => {
    setPhotos((p) => { const n = { ...p }; delete n[angle]; return n; });
    setResults((r) => { const n = { ...r }; delete n[angle]; return n; });
  };

  const resetAll = () => {
    setPhotos({}); 
    setResults({}); 
    setLoading({}); 
    setOverallScore(null);
    localStorage.removeItem("latest_posture_results");
  };

  const analyzeAll = async () => {
    const toAnalyze = Object.entries(photos).filter(([, f]) => f);
    if (!toAnalyze.length) { 
      toast.error("Upload at least one photo first."); 
      return; 
    }

    const updatedResults = { ...results };

    for (const [angle, file] of toAnalyze) {
      setLoading((l) => ({ ...l, [angle]: true }));
      try {
        const data = await postureService.analyzeSingle(file, angle);
        updatedResults[angle] = data;
        setResults((r) => ({ ...r, [angle]: data }));
        toast.success(`${angle.charAt(0).toUpperCase() + angle.slice(1)} view analyzed successfully!`);
      } catch (err) {
        toast.error(`${angle}: ${err.message || "Analysis failed."}`);
      } finally {
        setLoading((l) => ({ ...l, [angle]: false }));
      }
    }

    // Weighted combined score calculation
    const weights = { front: 0.4, back: 0.25, left: 0.2, right: 0.15 };
    let total = 0;
    let wSum = 0;

    Object.entries(updatedResults).forEach(([a, res]) => {
      if (res?.posture_score != null && weights[a]) {
        total += res.posture_score * weights[a];
        wSum  += weights[a];
      }
    });

    const calculatedOverall = wSum > 0 ? Math.round(total / wSum) : null;
    if (calculatedOverall != null) {
      setOverallScore(calculatedOverall);
    }

    // Save state to local storage so navigation doesn't clear results
    localStorage.setItem(
      "latest_posture_results",
      JSON.stringify({ results: updatedResults, overallScore: calculatedOverall })
    );
  };

  const analyzedCount = Object.values(results).filter(Boolean).length;

  return (
    <>
      <Topbar
        title="Posture Analysis Studio"
        subtitle="Upload up to 4 photos for a full-body posture scan powered by MediaPipe"
        onMenuClick={onMenuClick}
        actions={
          <div className="flex items-center gap-2">
            {analyzedCount > 0 && (
              <button onClick={resetAll} className="btn-ghost text-xs">
                <RotateCcw size={14} /> Reset
              </button>
            )}
            <button
              onClick={analyzeAll}
              disabled={!Object.keys(photos).length || Object.values(loading).some(Boolean)}
              className="btn-primary"
            >
              {Object.values(loading).some(Boolean) ? (
                <Spinner size={15} />
              ) : (
                <ScanFace size={15} />
              )}
              Analyze Photos
            </button>
          </div>
        }
      />

      <main className="p-4 lg:p-8 max-w-7xl mx-auto space-y-6">
        {/* Instructions banner */}
        <div className="flex items-start gap-3 p-4 rounded-xl bg-primary/5 border border-primary/20">
          <Info size={16} className="text-primary mt-0.5 shrink-0" />
          <div className="text-sm text-text-secondary space-y-1">
            <p className="font-medium text-text-primary">How to get the best results</p>
            <ul className="list-disc list-inside text-xs space-y-0.5">
              <li>Wear form-fitting clothing so landmarks are visible</li>
              <li>Stand 2–3 meters from camera, full body in frame</li>
              <li>Good lighting, no busy backgrounds</li>
              <li>Natural relaxed stance — don't try to correct your posture</li>
            </ul>
          </div>
        </div>

        {/* Overall score */}
        {overallScore != null && (
          <div className="card-glow p-6 flex items-center gap-8 animate-fade-in">
            <ScoreRing score={overallScore} size={110} strokeWidth={10} label="Overall Score" />
            <div className="flex-1 space-y-2">
              <h3 className="font-display text-xl font-semibold">
                {overallScore >= 80 ? "Excellent Posture" : overallScore >= 60 ? "Room to Improve" : "Needs Attention"}
              </h3>
              <p className="text-sm text-text-secondary">
                Based on {analyzedCount} angle{analyzedCount > 1 ? "s" : ""} analyzed. A score above 80 indicates
                well-aligned posture.
              </p>
              {analyzedCount < 4 && (
                <p className="text-xs text-text-muted flex items-center gap-1">
                  <ChevronRight size={12} className="text-primary" />
                  Add all 4 angles for a more accurate combined score
                </p>
              )}
            </div>
          </div>
        )}

        {/* Angle slots */}
        <div>
          <h2 className="section-title mb-4">Photo Upload Slots</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            {ANGLES.map((angle) => (
              <AngleSlot
                key={angle.key}
                angle={angle}
                file={photos[angle.key] || null}
                result={results[angle.key] || null}
                loading={!!loading[angle.key]}
                onDrop={handleDrop}
                onClear={handleClear}
              />
            ))}
          </div>
        </div>

        {/* All warnings aggregated */}
        {analyzedCount > 0 && (
          <div className="card p-6">
            <h2 className="section-title mb-4">Analysis Findings</h2>
            {Object.values(results).flatMap((r) => r?.warnings || []).length === 0 ? (
              <div className="flex items-center gap-2 text-accent text-sm">
                <CheckCircle size={16} /> No posture warnings detected — great alignment!
              </div>
            ) : (
              <div className="space-y-2">
                {Object.values(results)
                  .flatMap((r) => r?.warnings || [])
                  .filter((v, i, a) => a.indexOf(v) === i)
                  .map((w, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 rounded-xl bg-warning/5 border border-warning/20">
                      <AlertTriangle size={15} className="text-warning mt-0.5 shrink-0" />
                      <p className="text-sm text-text-secondary">{w}</p>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}
      </main>
    </>
  ); 
}