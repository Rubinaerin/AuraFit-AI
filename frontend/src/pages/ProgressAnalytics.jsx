import React, { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import {
  TrendingUp, Upload, BarChart3, ArrowUp, ArrowDown,
  Minus, CheckCircle, AlertTriangle, Trophy,
} from "lucide-react";
import {
  RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, Cell,
} from "recharts";
import toast from "react-hot-toast";
import Topbar from "../components/layout/Topbar";
import ScoreRing from "../components/ui/ScoreRing";
import Spinner from "../components/ui/Spinner";
import EmptyState from "../components/ui/EmptyState";
import { postureService } from "../services/postureService";

const ANGLES = ["front", "back", "left", "right"];
const ANGLE_LABELS = { front: "Front", back: "Back", left: "Left", right: "Right" };

const METRIC_META = {
  shoulder_tilt_deg:     { label: "Shoulder Tilt",      inverted: true },
  hip_tilt_deg:          { label: "Hip Tilt",           inverted: true },
  spine_lateral_dev_deg: { label: "Spine Lateral",      inverted: true },
  head_forward_deg:      { label: "Head Forward",       inverted: true },
  torso_lean_deg:        { label: "Torso Lean",         inverted: true },
};

/** Custom bar chart tooltip */
function DeltaTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { value, name } = payload[0];
  const improved = value < 0; // lower angle = better
  return (
    <div className="bg-card border border-border rounded-xl px-3 py-2 text-xs shadow-card">
      <p className="font-medium text-text-primary mb-0.5">{name}</p>
      <p className={improved ? "text-accent" : "text-danger"}>
        {value > 0 ? "+" : ""}{value?.toFixed(2)}°
        <span className="text-text-muted ml-1">{improved ? "improved" : "worsened"}</span>
      </p>
    </div>
  );
}

function DeltaBadge({ delta, inverted = true }) {
  if (delta == null) return <span className="badge badge-muted">N/A</span>;
  const positive = inverted ? delta < 0 : delta > 0;
  const abs = Math.abs(delta);
  if (abs < 0.5) return (
    <span className="badge badge-muted flex items-center gap-1"><Minus size={10} />Stable</span>
  );
  return positive
    ? <span className="badge badge-accent flex items-center gap-1"><ArrowDown size={10} />-{abs.toFixed(1)}°</span>
    : <span className="badge badge-danger flex items-center gap-1"><ArrowUp size={10} />+{abs.toFixed(1)}°</span>;
}

export default function ProgressAnalytics() {
  const { onMenuClick } = useOutletContext() || {};
  const [selectedAngle, setSelectedAngle] = useState("front");
  const [baselineMonth, setBaselineMonth] = useState(1);
  const [newMonth, setNewMonth] = useState(2);
  const [newPhoto, setNewPhoto] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (files) => { if (files[0]) setNewPhoto(files[0]); },
    accept: { "image/jpeg": [], "image/png": [], "image/webp": [] },
    multiple: false,
  });

  const runComparison = async () => {
    if (!newPhoto) { toast.error("Please upload your new month's photo."); return; }
    setLoading(true);
    setResult(null);
    try {
      const data = await postureService.comparePosture({
        photo: newPhoto,
        angle: selectedAngle,
        newMonthNumber: newMonth,
        baselineMonth,
      });
      setResult(data);
      toast.success("Progress comparison complete!");
    } catch (err) {
      toast.error(err.message || "Comparison failed.");
    } finally {
      setLoading(false);
    }
  };

  /* ── Build chart datasets from result ── */
  const deltaBarData = result
    ? Object.entries(result.metrics || {})
        .filter(([k]) => METRIC_META[k])
        .map(([k, v]) => ({
          name: METRIC_META[k]?.label,
          delta: v?.delta ?? 0,
        }))
    : [];

  const radarData = result
    ? Object.entries(result.metrics || {})
        .filter(([k]) => METRIC_META[k])
        .map(([k, v]) => ({
          metric: METRIC_META[k]?.label,
          baseline: Math.abs(v?.baseline ?? 0),
          current:  Math.abs(v?.new ?? 0),
        }))
    : [];

  const report = result?.ai_report || {};
  const improvedCount = result?.improved_count ?? 0;
  const worsenedCount = result?.worsened_count ?? 0;

  return (
    <>
      <Topbar
        title="Progress Analytics"
        subtitle="Compare posture metrics across months to visualize your improvement journey"
        onMenuClick={onMenuClick}
      />

      <main className="p-4 lg:p-8 max-w-6xl mx-auto space-y-6">
        {/* Configuration card */}
        <div className="card p-6 space-y-5">
          <h2 className="section-title">Comparison Setup</h2>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-xs font-medium text-text-secondary mb-1.5 block">Photo Angle</label>
              <select className="select-field" value={selectedAngle}
                onChange={(e) => setSelectedAngle(e.target.value)}>
                {ANGLES.map((a) => <option key={a} value={a}>{ANGLE_LABELS[a]}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-text-secondary mb-1.5 block">Baseline Month</label>
              <select className="select-field" value={baselineMonth}
                onChange={(e) => setBaselineMonth(Number(e.target.value))}>
                {[1,2,3,4,5,6].map((m) => <option key={m} value={m}>Month {m}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-text-secondary mb-1.5 block">Current Month</label>
              <select className="select-field" value={newMonth}
                onChange={(e) => setNewMonth(Number(e.target.value))}>
                {[2,3,4,5,6,7,8,9,10,11,12].map((m) => <option key={m} value={m}>Month {m}</option>)}
              </select>
            </div>
          </div>

          {/* Photo upload */}
          <div>
            <label className="text-xs font-medium text-text-secondary mb-1.5 block">
              Upload Month {newMonth} — {ANGLE_LABELS[selectedAngle]} View Photo
            </label>
            {!newPhoto ? (
              <div
                {...getRootProps()}
                className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-xl p-8 cursor-pointer transition-colors ${
                  isDragActive ? "border-primary bg-primary/5" : "border-border hover:border-primary/40 hover:bg-primary/5"
                }`}
              >
                <input {...getInputProps()} />
                <Upload size={24} className="text-text-muted" />
                <p className="text-sm text-text-secondary">Drag & drop or click to upload</p>
                <p className="text-xs text-text-muted">JPG, PNG or WebP · max 10 MB</p>
              </div>
            ) : (
              <div className="flex items-center gap-4 p-3 rounded-xl bg-surface border border-border">
                <img
                  src={URL.createObjectURL(newPhoto)}
                  alt="preview"
                  className="w-16 h-16 rounded-lg object-cover"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-text-primary truncate">{newPhoto.name}</p>
                  <p className="text-xs text-text-muted">{(newPhoto.size / 1024).toFixed(0)} KB</p>
                </div>
                <button onClick={() => setNewPhoto(null)}
                  className="text-xs text-text-muted hover:text-danger">Remove</button>
              </div>
            )}
          </div>

          <button onClick={runComparison} disabled={loading || !newPhoto} className="btn-primary">
            {loading ? <Spinner size={16} label="Analyzing…" /> : <><BarChart3 size={16} /> Run Comparison</>}
          </button>
        </div>

        {/* Results */}
        {result && (
          <div className="space-y-6 animate-slide-up">
            {/* Score comparison row */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="card p-5 flex flex-col items-center gap-2">
                <p className="text-xs text-text-muted uppercase tracking-wide">Baseline Score</p>
                <ScoreRing score={result.scores?.baseline_score} size={80} strokeWidth={7} />
                <p className="text-xs text-text-secondary">Month {baselineMonth}</p>
              </div>
              <div className="card-glow p-5 flex flex-col items-center justify-center gap-2">
                <p className="text-xs text-text-muted uppercase tracking-wide">Score Change</p>
                <p className={`font-display text-4xl font-bold ${
                  (result.scores?.score_change ?? 0) >= 0 ? "text-accent" : "text-danger"
                }`}>
                  {(result.scores?.score_change ?? 0) >= 0 ? "+" : ""}
                  {result.scores?.score_change?.toFixed(1) ?? "—"}
                </p>
                <span className={`badge ${(result.scores?.score_change ?? 0) >= 0 ? "badge-accent" : "badge-danger"}`}>
                  {(result.scores?.score_change ?? 0) >= 0
                    ? `${improvedCount} metrics improved`
                    : `${worsenedCount} metrics worsened`}
                </span>
              </div>
              <div className="card p-5 flex flex-col items-center gap-2">
                <p className="text-xs text-text-muted uppercase tracking-wide">Current Score</p>
                <ScoreRing score={result.scores?.new_score} size={80} strokeWidth={7} />
                <p className="text-xs text-text-secondary">Month {newMonth}</p>
              </div>
            </div>

            {/* Summary text */}
            {result.summary && (
              <div className="flex items-start gap-3 p-4 rounded-xl bg-accent/5 border border-accent/20">
                <Trophy size={18} className="text-accent mt-0.5 shrink-0" />
                <p className="text-sm text-text-primary">{result.summary}</p>
              </div>
            )}

            {/* Charts row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Delta bar chart */}
              <div className="card p-5">
                <h3 className="section-title mb-1">Metric Deltas</h3>
                <p className="section-subtitle mb-4">Negative = improvement (angle decreased)</p>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={deltaBarData} layout="vertical" margin={{ left: 16 }}>
                    <XAxis type="number" domain={["auto", "auto"]} tick={{ fill: "#9999BB", fontSize: 11 }} />
                    <YAxis type="category" dataKey="name" width={110} tick={{ fill: "#9999BB", fontSize: 11 }} />
                    <Tooltip content={<DeltaTooltip />} />
                    <ReferenceLine x={0} stroke="#2A2A3E" />
                    <Bar dataKey="delta" radius={[0, 4, 4, 0]}>
                      {deltaBarData.map((entry, i) => (
                        <Cell
                          key={i}
                          fill={entry.delta <= 0 ? "#00D4AA" : "#FF4757"}
                          fillOpacity={0.8}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Radar overlay */}
              <div className="card p-5">
                <h3 className="section-title mb-1">Posture Overlay</h3>
                <p className="section-subtitle mb-4">Lower values = better alignment (degrees)</p>
                <ResponsiveContainer width="100%" height={220}>
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#2A2A3E" />
                    <PolarAngleAxis dataKey="metric" tick={{ fill: "#9999BB", fontSize: 10 }} />
                    <Radar name={`Month ${baselineMonth}`} dataKey="baseline"
                      stroke="#6C63FF" fill="#6C63FF" fillOpacity={0.15} strokeWidth={2} />
                    <Radar name={`Month ${newMonth}`} dataKey="current"
                      stroke="#00D4AA" fill="#00D4AA" fillOpacity={0.15} strokeWidth={2} />
                  </RadarChart>
                </ResponsiveContainer>
                <div className="flex justify-center gap-5 mt-2">
                  <span className="text-xs flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-primary inline-block rounded" /> Month {baselineMonth}
                  </span>
                  <span className="text-xs flex items-center gap-1.5">
                    <span className="w-3 h-0.5 bg-accent inline-block rounded" /> Month {newMonth}
                  </span>
                </div>
              </div>
            </div>

            {/* Per-metric table */}
            <div className="card p-6">
              <h3 className="section-title mb-4">Metric Breakdown</h3>
              <div className="space-y-0 divide-y divide-border">
                {Object.entries(result.metrics || {})
                  .filter(([k]) => METRIC_META[k])
                  .map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between py-3">
                      <span className="text-sm text-text-secondary">{METRIC_META[k]?.label}</span>
                      <div className="flex items-center gap-4">
                        <span className="text-xs text-text-muted w-14 text-right">
                          {v?.baseline?.toFixed(1)}° → {v?.new?.toFixed(1)}°
                        </span>
                        <DeltaBadge delta={v?.delta} inverted={METRIC_META[k]?.inverted} />
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {/* AI Narrative report */}
            {report.overall_verdict && (
              <div className="card p-6 space-y-4">
                <h3 className="section-title">AI Coach Assessment</h3>
                <p className="text-sm text-text-primary font-medium">{report.overall_verdict}</p>
                {report.score_change_comment && (
                  <p className="text-sm text-text-secondary">{report.score_change_comment}</p>
                )}

                {report.highlights?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-accent uppercase tracking-wide mb-2">Highlights</p>
                    <ul className="space-y-1">
                      {report.highlights.map((h, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                          <CheckCircle size={14} className="text-accent mt-0.5 shrink-0" />{h}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {report.areas_to_focus?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-warning uppercase tracking-wide mb-2">Areas to Focus</p>
                    <ul className="space-y-1">
                      {report.areas_to_focus.map((a, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                          <AlertTriangle size={14} className="text-warning mt-0.5 shrink-0" />{a}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {report.motivational_note && (
                  <div className="p-3 rounded-xl bg-primary/5 border border-primary/15">
                    <p className="text-sm text-text-primary italic">"{report.motivational_note}"</p>
                  </div>
                )}

                {report.next_month_tips?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-2">Next Month Tips</p>
                    <ol className="space-y-1 list-decimal list-inside">
                      {report.next_month_tips.map((t, i) => (
                        <li key={i} className="text-sm text-text-secondary">{t}</li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!result && !loading && (
          <EmptyState
            icon={TrendingUp}
            title="No comparison run yet"
            description="Configure your months above, upload your new photo, and click Run Comparison to see your progress."
          />
        )}
      </main>
    </>
  );
}
