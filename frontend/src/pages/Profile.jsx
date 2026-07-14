/**
 * Profile.jsx — AuraFit AI Adaptive Profile Dashboard
 *
 * Provides real-time mutation of user biometrics and health condition state
 * without requiring a page reload or code change. All edits are applied to
 * both local component state AND the global AuthContext (via setUser) so
 * that downstream pages — particularly CoachChat.jsx — immediately receive
 * the updated profile on their next interaction.
 *
 * Sections:
 *   1. Profile Identity Card  — avatar, name badge, account metadata
 *   2. Biometric Editor       — inline editable fields for physical metrics
 *   3. Injury Toggle Matrix   — state-driven switches that mutate health_conditions
 *   4. Save / Sync Panel      — persists changes to the backend via PATCH /users/me
 */

import React, { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import toast from "react-hot-toast";
import {
  User as UserIcon,
  Ruler,
  Weight,
  Target,
  Activity,
  Save,
  RefreshCw,
  ShieldAlert,
  CheckCircle,
  AlertTriangle,
  Zap,
  Info,
} from "lucide-react";

import { useAuth } from "../hooks/useAuth";
import api from "../services/api";

// ─── Injury toggle configuration (mirrors ConditionTypeEnum in the backend) ──

const INJURY_DEFINITIONS = [
  {
    key: "lumbar_hernia",
    label: "Lumbar Hernia",
    shortLabel: "Lower Back",
    desc: "Restricts deadlifts, good-mornings, sit-ups, and bent-over rows.",
    bodyRegion: "lower_back",
    color: "text-danger",
    bgActive: "bg-danger/10 border-danger/30",
    iconBg: "bg-danger/10",
  },
  {
    key: "knee_injury",
    label: "Knee Injury",
    shortLabel: "Knee",
    desc: "Restricts deep squats (90°+), heavy leg extensions, and box jumps.",
    bodyRegion: "knee",
    color: "text-warning",
    bgActive: "bg-warning/10 border-warning/30",
    iconBg: "bg-warning/10",
  },
  {
    key: "shoulder_injury",
    label: "Shoulder Injury",
    shortLabel: "Shoulder",
    desc: "Restricts behind-neck press, upright rows, and heavy dips.",
    bodyRegion: "shoulder",
    color: "text-primary",
    bgActive: "bg-primary/10 border-primary/30",
    iconBg: "bg-primary/10",
  },
  {
    key: "hypertension",
    label: "Hypertension",
    shortLabel: "Blood Pressure",
    desc: "Restricts maximal isometric holds and Valsalva-heavy lifts.",
    bodyRegion: "cardiovascular",
    color: "text-accent",
    bgActive: "bg-accent/10 border-accent/30",
    iconBg: "bg-accent/10",
  },
  {
    key: "diabetes",
    label: "Diabetes",
    shortLabel: "Diabetes",
    desc: "Requires careful blood glucose monitoring around exercise sessions.",
    bodyRegion: "metabolic",
    color: "text-warning",
    bgActive: "bg-warning/10 border-warning/30",
    iconBg: "bg-warning/10",
  },
  {
    key: "heart_condition",
    label: "Heart Condition",
    shortLabel: "Cardiac",
    desc: "Limits intensity to <70% HRmax; mandates warm-up and cool-down.",
    bodyRegion: "cardiovascular",
    color: "text-danger",
    bgActive: "bg-danger/10 border-danger/30",
    iconBg: "bg-danger/10",
  },
];

const FITNESS_LEVELS = ["beginner", "intermediate", "advanced"];
const SEVERITY_OPTIONS = ["mild", "moderate", "severe"];

// ─── Reusable toggle switch component ────────────────────────────────────────

function ToggleSwitch({ checked, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary/40 ${
        checked ? "bg-primary" : "bg-border"
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200 ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

// ─── Inline editable metric field ────────────────────────────────────────────

function MetricField({ icon: Icon, label, value, onChange, type = "number", unit, min, max, readOnly = false }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-text-secondary mb-1.5 uppercase tracking-wide">
        {label}{unit && <span className="text-text-muted font-normal ml-1 normal-case">({unit})</span>}
      </label>
      <div className="relative">
        <Icon size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
        {readOnly ? (
          <div className="input-field pl-10 cursor-default opacity-60">{value || "—"}</div>
        ) : (
          <input
            type={type}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            min={min}
            max={max}
            className="input-field pl-10"
          />
        )}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Profile() {
  const { user, setUser } = useAuth();
  // useOutletContext is available when rendered inside DashboardLayout
  const outletCtx = useOutletContext();
  const onMenuClick = outletCtx?.onMenuClick;

  // ── Initialise editable fields from the authenticated user object ─────────
  const [fullName,     setFullName]     = useState(user?.full_name          || "");
  const [heightCm,     setHeightCm]     = useState(user?.height_cm          || "");
  const [currentWeight,setCurrentWeight]= useState(user?.current_weight_kg  || "");
  const [targetWeight, setTargetWeight] = useState(user?.target_weight_kg   || "");
  const [fitnessLevel, setFitnessLevel] = useState(user?.fitness_level      || "beginner");

  // Build active injury state from the user's stored health_conditions array.
  const buildInitialInjuryState = React.useCallback(() => {
    const active   = {};
    const severity = {};
    (user?.health_conditions || []).forEach((cond) => {
      if (cond.is_active !== false) {
        active[cond.condition_type]   = true;
        severity[cond.condition_type] = cond.severity || "moderate";
      }
    });
    return { active, severity };
  }, [user]);

  const [activeInjuries, setActiveInjuries] = useState(() => buildInitialInjuryState().active);
  const [severityMap,    setSeverityMap]    = useState(() => buildInitialInjuryState().severity);
  const [saving, setSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  // Re-sync local fields if the global user object changes externally
  useEffect(() => {
    if (!user) return;
    setFullName(user.full_name         || "");
    setHeightCm(user.height_cm         || "");
    setCurrentWeight(user.current_weight_kg || "");
    setTargetWeight(user.target_weight_kg   || "");
    setFitnessLevel(user.fitness_level      || "beginner");
    const { active, severity } = buildInitialInjuryState();
    setActiveInjuries(active);
    setSeverityMap(severity);
    setIsDirty(false);
  }, [user, buildInitialInjuryState]);

  // ── Injury toggle — mutates local state AND global AuthContext immediately ─
  const handleInjuryToggle = (key, isActive) => {
    const nextActive = { ...activeInjuries, [key]: isActive };
    if (!isActive) {
      const next = { ...nextActive };
      delete next[key];
      setActiveInjuries(next);
    } else {
      setActiveInjuries(nextActive);
      setSeverityMap((m) => ({ ...m, [key]: m[key] || "moderate" }));
    }
    setIsDirty(true);

    // ── Immediate global state update ────────────────────────────────────────
    // This is the key integration point: CoachChat reads user.health_conditions
    // from the AuthContext on every message send. By updating setUser here, the
    // next chatbot call will automatically carry the new injury profile without
    // requiring a page reload or re-authentication.
    if (setUser && user) {
      const conditionsDef = INJURY_DEFINITIONS.find((d) => d.key === key);
      const existingConditions = (user.health_conditions || []).filter(
        (c) => c.condition_type !== key
      );
      const updatedConditions = isActive
        ? [
            ...existingConditions,
            {
              condition_type:  key,
              severity:        severityMap[key] || "moderate",
              affected_region: conditionsDef?.bodyRegion || null,
              is_active:       true,
              description:     null,
            },
          ]
        : existingConditions;

      setUser({ ...user, health_conditions: updatedConditions });
    }
  };

  const handleSeverityChange = (key, severity) => {
    setSeverityMap((m) => ({ ...m, [key]: severity }));
    setIsDirty(true);
    // Propagate severity change to global user context as well
    if (setUser && user) {
      const updatedConditions = (user.health_conditions || []).map((c) =>
        c.condition_type === key ? { ...c, severity } : c
      );
      setUser({ ...user, health_conditions: updatedConditions });
    }
  };

  // ── Persist to backend via PATCH /users/me ────────────────────────────────
  const handleSave = async () => {
    if (!fullName.trim()) {
      toast.error("Full name cannot be empty.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        physical_data: {
          height_cm:         Number(heightCm),
          current_weight_kg: Number(currentWeight),
          target_weight_kg:  Number(targetWeight),
          gender:            user?.gender || "other",
          fitness_level:     fitnessLevel,
          primary_goal:      user?.primary_goal || "weight_loss",
        },
        health_conditions: Object.entries(activeInjuries)
          .filter(([, active]) => active)
          .map(([condType]) => {
            const def = INJURY_DEFINITIONS.find((d) => d.key === condType);
            return {
              condition_type:  condType,
              severity:        severityMap[condType] || "moderate",
              affected_region: def?.bodyRegion || null,
              description:     null,
            };
          }),
      };

      const { data } = await api.patch("/users/me", payload);

      // Merge backend response into global AuthContext.
      // full_name is not part of the PATCH schema currently, so we merge it
      // manually from local state.
      if (setUser) {
        setUser({ ...data, full_name: fullName.trim() });
      }
      setIsDirty(false);
      toast.success("Profile updated successfully. FitCoach will use the new data immediately.");
    } catch (err) {
      toast.error(err.message || "Failed to save profile. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!user) return;
    setFullName(user.full_name          || "");
    setHeightCm(user.height_cm          || "");
    setCurrentWeight(user.current_weight_kg || "");
    setTargetWeight(user.target_weight_kg   || "");
    setFitnessLevel(user.fitness_level      || "beginner");
    const { active, severity } = buildInitialInjuryState();
    setActiveInjuries(active);
    setSeverityMap(severity);
    setIsDirty(false);
    toast("Changes discarded.", { icon: "↩️" });
  };

  const activeCount = Object.values(activeInjuries).filter(Boolean).length;

  // ─── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-base">

      {/* ── Topbar ──────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-20 flex items-center justify-between h-16 px-4 lg:px-8 bg-base/80 backdrop-blur-md border-b border-border">
        <div className="flex items-center gap-3">
          {onMenuClick && (
            <button onClick={onMenuClick} className="lg:hidden text-text-secondary hover:text-text-primary">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
            </button>
          )}
          <div>
            <h1 className="font-display font-semibold text-lg leading-tight">Profile</h1>
            <p className="text-xs text-text-muted">Adaptive Dashboard — changes propagate to FitCoach instantly</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isDirty && (
            <button onClick={handleReset} className="btn-ghost text-xs">
              <RefreshCw size={14} /> Discard
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving || !isDirty}
            className="btn-primary"
          >
            {saving ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Saving…
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Save size={15} /> Save Changes
              </span>
            )}
          </button>
        </div>
      </header>

      <main className="p-4 lg:p-8 max-w-5xl mx-auto space-y-6">

        {/* ── 1. Profile Identity Card ───────────────────────────────────── */}
        <div className="card-glow p-6 flex flex-col sm:flex-row items-start sm:items-center gap-5">
          {/* Avatar */}
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shrink-0 shadow-glow-primary">
            <span className="font-display text-2xl font-bold text-white">
              {fullName?.[0]?.toUpperCase() || "A"}
            </span>
          </div>

          <div className="flex-1 min-w-0">
            {/* Inline name edit */}
            <input
              type="text"
              value={fullName}
              onChange={(e) => { setFullName(e.target.value); setIsDirty(true); }}
              className="bg-transparent font-display text-xl font-bold text-text-primary border-b border-transparent hover:border-border focus:border-primary focus:outline-none w-full transition-colors"
              placeholder="Your full name"
              aria-label="Full name"
            />
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className="badge badge-primary">{user?.fitness_level || "beginner"}</span>
              <span className="badge badge-muted">
                {user?.primary_goal?.replace(/_/g, " ") || "—"}
              </span>
              {activeCount > 0 && (
                <span className="badge badge-danger">
                  {activeCount} active condition{activeCount > 1 ? "s" : ""}
                </span>
              )}
            </div>
            <p className="text-xs text-text-muted mt-1">{user?.email}</p>
          </div>

          {/* Realtime propagation indicator */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-accent/5 border border-accent/20">
            <span className="glow-dot" />
            <span className="text-[11px] text-accent font-medium">Live Sync</span>
          </div>
        </div>

        {/* ── 2. Biometric Editor ─────────────────────────────────────────── */}
        <div className="card p-6">
          <h2 className="section-title mb-1">Biometric Profile</h2>
          <p className="section-subtitle mb-5">
            Updating these values recalibrates workout volume and goal timeline estimates.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <MetricField
              icon={Ruler}
              label="Height"
              unit="cm"
              value={heightCm}
              onChange={(v) => { setHeightCm(v); setIsDirty(true); }}
              min={100}
              max={250}
            />
            <MetricField
              icon={Weight}
              label="Current Weight"
              unit="kg"
              value={currentWeight}
              onChange={(v) => { setCurrentWeight(v); setIsDirty(true); }}
              min={30}
              max={300}
            />
            <MetricField
              icon={Target}
              label="Target Weight"
              unit="kg"
              value={targetWeight}
              onChange={(v) => { setTargetWeight(v); setIsDirty(true); }}
              min={30}
              max={300}
            />

            {/* Derived BMI — read-only */}
            <MetricField
              icon={Activity}
              label="BMI (calculated)"
              value={
                heightCm && currentWeight
                  ? (Number(currentWeight) / (Number(heightCm) / 100) ** 2).toFixed(1)
                  : "—"
              }
              onChange={() => {}}
              readOnly
            />

            {/* Birth year — read-only after registration */}
            <MetricField
              icon={UserIcon}
              label="Birth Year"
              value={user?.birth_year || "—"}
              onChange={() => {}}
              readOnly
            />

            {/* Fitness level */}
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1.5 uppercase tracking-wide">
                Fitness Level
              </label>
              <select
                className="select-field"
                value={fitnessLevel}
                onChange={(e) => { setFitnessLevel(e.target.value); setIsDirty(true); }}
              >
                {FITNESS_LEVELS.map((l) => (
                  <option key={l} value={l}>{l[0].toUpperCase() + l.slice(1)}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* ── 3. Live Injury Toggle Matrix ───────────────────────────────── */}
        <div className="card p-6">
          <div className="flex items-center justify-between mb-1">
            <h2 className="section-title">Interactive Injury Body Map</h2>
            <span className="badge badge-muted">{activeCount} / {INJURY_DEFINITIONS.length} active</span>
          </div>
          <p className="section-subtitle mb-2">
            Toggle any condition to immediately update FitCoach AI's exercise safety filters.
          </p>

          {/* Real-time propagation notice */}
          <div className="flex items-start gap-2 p-3 rounded-xl bg-primary/5 border border-primary/15 mb-5">
            <Zap size={13} className="text-primary mt-0.5 shrink-0" />
            <p className="text-[11px] text-text-secondary leading-relaxed">
              Changes to this matrix are applied to the global session state immediately.
              The next message you send to FitCoach Chat will reflect the updated injury profile
              — no page reload required.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {INJURY_DEFINITIONS.map((inj) => {
              const isActive = !!activeInjuries[inj.key];
              return (
                <div
                  key={inj.key}
                  className={`p-4 rounded-xl border transition-all duration-200 ${
                    isActive ? inj.bgActive : "bg-surface border-border"
                  }`}
                >
                  {/* Toggle row */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 flex-1 min-w-0">
                      <div className={`w-8 h-8 rounded-lg ${inj.iconBg} flex items-center justify-center shrink-0 mt-0.5`}>
                        <ShieldAlert size={15} className={inj.color} />
                      </div>
                      <div className="min-w-0">
                        <p className={`text-sm font-semibold ${isActive ? inj.color : "text-text-primary"}`}>
                          {inj.label}
                        </p>
                        <p className="text-[11px] text-text-muted leading-relaxed mt-0.5">{inj.desc}</p>
                      </div>
                    </div>
                    <ToggleSwitch
                      checked={isActive}
                      onChange={(val) => handleInjuryToggle(inj.key, val)}
                      label={`Toggle ${inj.label}`}
                    />
                  </div>

                  {/* Severity picker — visible only when the condition is toggled on */}
                  {isActive && (
                    <div className="mt-3 pt-3 border-t border-border/60">
                      <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wide mb-2">
                        Severity
                      </p>
                      <div className="flex gap-1.5">
                        {SEVERITY_OPTIONS.map((sev) => {
                          const selected = (severityMap[inj.key] || "moderate") === sev;
                          return (
                            <button
                              key={sev}
                              type="button"
                              onClick={() => handleSeverityChange(inj.key, sev)}
                              className={`flex-1 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wide transition-all ${
                                selected
                                  ? sev === "mild"
                                    ? "bg-accent/20 text-accent border border-accent/40"
                                    : sev === "moderate"
                                    ? "bg-warning/20 text-warning border border-warning/40"
                                    : "bg-danger/20 text-danger border border-danger/40"
                                  : "bg-base text-text-muted border border-border hover:border-primary/25"
                              }`}
                            >
                              {sev}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── 4. Status summary card ──────────────────────────────────────── */}
        <div className="card p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
          {activeCount === 0 ? (
            <>
              <CheckCircle size={20} className="text-accent shrink-0" />
              <div>
                <p className="text-sm font-semibold text-text-primary">No active conditions</p>
                <p className="text-xs text-text-muted">
                  AuraFit AI will generate unrestricted programming. Toggle conditions above if applicable.
                </p>
              </div>
            </>
          ) : (
            <>
              <AlertTriangle size={20} className="text-warning shrink-0" />
              <div>
                <p className="text-sm font-semibold text-text-primary">
                  {activeCount} condition{activeCount > 1 ? "s" : ""} active
                </p>
                <p className="text-xs text-text-muted">
                  FitCoach AI and the Workout Engine will automatically exclude contraindicated
                  exercises and apply appropriate safety notes.
                </p>
              </div>
            </>
          )}

          {isDirty && (
            <div className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-warning/5 border border-warning/20">
              <Info size={12} className="text-warning" />
              <span className="text-[11px] text-warning font-medium">Unsaved changes</span>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
