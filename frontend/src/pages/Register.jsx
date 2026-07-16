/**
 * Register.jsx — AuraFit AI Onboarding Pipeline
 *
 * Implements a 3-step wizard form that progressively collects:
 *   Step 1 — Account Credentials   (name, email, password)
 *   Step 2 — Biometric Profile     (gender, birth year, height, weight, fitness level)
 *   Step 3 — Injury & Goal Matrix  (primary goal, health conditions, data consent)
 *
 * On completion the assembled payload is sent to POST /auth/register.
 * The returned JWT is stored and the global AuthContext is hydrated before
 * the user is redirected to /posture.
 */

import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  Activity,
  User as UserIcon,
  Mail,
  Lock,
  Eye,
  EyeOff,
  ArrowRight,
  ArrowLeft,
  Check,
  ShieldCheck,
  Ruler,
  Weight,
  Calendar,
  Target,
  AlertTriangle,
} from "lucide-react";

import { useAuth } from "../hooks/useAuth";
import api from "../services/api";

// ─── Static configuration data ────────────────────────────────────────────────

const FITNESS_LEVELS = [
  { value: "beginner",     label: "Beginner"     },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced",     label: "Advanced"     },
];

const PRIMARY_GOALS = [
  { value: "weight_loss",   label: "Weight Loss"            },
  { value: "muscle_gain",   label: "Muscle Gain"            },
  { value: "endurance",     label: "Endurance & Cardio"     },
  { value: "flexibility",   label: "Flexibility & Mobility" },
  { value: "rehabilitation",label: "Rehabilitation"          },
];

// Each entry maps directly to the backend's ConditionTypeEnum values.
const HEALTH_CONDITIONS = [
  {
    value: "lumbar_hernia",
    label: "Lumbar Hernia",
    desc: "Lower back disc herniation",
    icon: "🔴",
  },
  {
    value: "knee_injury",
    label: "Knee Injury",
    desc: "Ligament, meniscus or cartilage damage",
    icon: "🟠",
  },
  {
    value: "shoulder_injury",
    label: "Shoulder Injury",
    desc: "Rotator cuff or impingement issues",
    icon: "🟡",
  },
  {
    value: "hypertension",
    label: "Hypertension",
    desc: "High blood pressure (cardiovascular)",
    icon: "🔵",
  },
  {
    value: "diabetes",
    label: "Diabetes",
    desc: "Blood glucose regulation disorder",
    icon: "🟣",
  },
  {
    value: "heart_condition",
    label: "Heart Condition",
    desc: "Cardiac or coronary artery condition",
    icon: "❤️",
  },
  {
    value: "other",
    label: "Other Condition",
    desc: "Any additional medical consideration",
    icon: "⚪",
  },
];

const SEVERITY_OPTIONS = ["mild", "moderate", "severe"];

// ─── Step progress indicator component ───────────────────────────────────────

function StepIndicator({ current, total }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {Array.from({ length: total }, (_, i) => {
        const step = i + 1;
        const done    = step < current;
        const active  = step === current;
        return (
          <React.Fragment key={step}>
            <div className={`flex items-center justify-center w-8 h-8 rounded-full text-xs font-bold transition-all duration-300 ${
              done   ? "bg-accent text-base"
            : active ? "bg-primary text-white shadow-glow-primary"
            :          "bg-border text-text-muted"
            }`}>
              {done ? <Check size={14} /> : step}
            </div>
            {step < total && (
              <div className={`flex-1 h-0.5 rounded-full transition-all duration-500 ${
                done ? "bg-accent" : "bg-border"
              }`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ─── Reusable labelled input wrapper ─────────────────────────────────────────

function FieldWrapper({ label, required, children }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-text-secondary mb-1.5 uppercase tracking-wide">
        {label}{required && <span className="text-danger ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Register() {
  const navigate    = useNavigate();
  const { refreshUser } = useAuth();

  const [step, setStep]     = useState(1);
  const [loading, setLoading] = useState(false);

  // Step 1 state
  const [fullName, setFullName]   = useState("");
  const [email, setEmail]         = useState("");
  const [password, setPassword]   = useState("");
  const [showPass, setShowPass]   = useState(false);

  // Step 2 state
  const [gender, setGender]           = useState("male");
  const [birthYear, setBirthYear]     = useState("");
  const [heightCm, setHeightCm]       = useState("");
  const [currentWeight, setCurrentWeight] = useState("");
  const [targetWeight, setTargetWeight]   = useState("");
  const [fitnessLevel, setFitnessLevel]   = useState("beginner");

  // Step 3 state
  const [primaryGoal, setPrimaryGoal]     = useState("weight_loss");
  const [selectedConditions, setSelectedConditions] = useState([]);
  // Severity map: { lumbar_hernia: "moderate", ... }
  const [severityMap, setSeverityMap] = useState({});
  const [consentGiven, setConsentGiven] = useState(false);

  // ── Condition toggle helpers ──────────────────────────────────────────────
  const toggleCondition = (value) => {
    setSelectedConditions((prev) => {
      if (prev.includes(value)) {
        // Remove condition and its severity entry
        setSeverityMap((m) => {
          const next = { ...m };
          delete next[value];
          return next;
        });
        return prev.filter((v) => v !== value);
      }
      setSeverityMap((m) => ({ ...m, [value]: "moderate" }));
      return [...prev, value];
    });
  };

  const setSeverity = (condition, severity) => {
    setSeverityMap((m) => ({ ...m, [condition]: severity }));
  };

  // ── Step validation ───────────────────────────────────────────────────────
  const canAdvanceStep1 = fullName.trim().length >= 2 && email.includes("@") && password.length >= 8;
  const canAdvanceStep2 =
    birthYear.length === 4 &&
    Number(birthYear) >= 1930 &&
    Number(birthYear) <= new Date().getFullYear() - 10 &&
    Number(heightCm) > 100 &&
    Number(heightCm) < 250 &&
    Number(currentWeight) > 30 &&
    Number(targetWeight) > 30 &&
    Math.abs(Number(currentWeight) - Number(targetWeight)) <= 100;

  // ── Final submission ──────────────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!consentGiven) {
      toast.error("You must accept the Biomechanical Consent & Data Protection agreement to proceed.");
      return;
    }

    setLoading(true);
    try {
      const payload = {
        user: {
          email:     email.trim().toLowerCase(),
          password:  password,
          full_name: fullName.trim(),
        },
        physical_data: {
          height_cm:          Number(heightCm),
          current_weight_kg:  Number(currentWeight),
          target_weight_kg:   Number(targetWeight),
          gender:             gender, // "male", "female", "other" (GenderEnum ile tam uyumlu)
          birth_year:         Number(birthYear),
          fitness_level:      fitnessLevel, // "beginner", "intermediate", "advanced"
          primary_goal:       primaryGoal, // "weight_loss", "muscle_gain" vb.
        },
        // Backend HealthConditionSchema'nın tam olarak beklediği alan adları:
        health_conditions: selectedConditions.map((condType) => ({
          condition_type:  condType, // schemas.py içindeki ConditionTypeEnum ile birebir eşleşir
          severity:        severityMap[condType] || "moderate",
          description:     `User self-reported ${condType} during registration.`, // Boş yerine anlamlı bir metin gönderiyoruz
          affected_region: condType === "lumbar_hernia" ? "lower_back" : 
                           condType === "knee_injury" ? "knee" : 
                           condType === "shoulder_injury" ? "shoulder" : null,
        })),
      };

      const { data } = await api.post("/auth/register", payload);
      localStorage.setItem("fitcore_token", data.access_token);
      await refreshUser();

      toast.success("Account created successfully! Welcome to AuraFit AI.");
      navigate("/posture");
    } catch (err) {
      toast.error(err.message || "Registration failed. Please review your inputs and try again.");
    } finally {
      setLoading(false);
    }
  };

  // ─── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-base flex items-start justify-center px-4 py-10">

      {/* Ambient glow */}
      <div className="fixed top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-primary/5 blur-3xl pointer-events-none" />

      <div className="w-full max-w-lg relative z-10">

        {/* Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-glow-primary mb-3">
            <Activity size={24} className="text-white" strokeWidth={2.5} />
          </div>
          <h1 className="font-display text-2xl font-bold text-text-primary">
            Create Your Account
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Step {step} of 3 — {step === 1 ? "Account Credentials" : step === 2 ? "Biometric Profile" : "Injury & Goal Matrix"}
          </p>
        </div>

        <div className="card p-6 animate-fade-in">
          <StepIndicator current={step} total={3} />

          {/* ── STEP 1: Account Credentials ─────────────────────────────── */}
          {step === 1 && (
            <div className="space-y-4 animate-slide-up">
              <FieldWrapper label="Full Name" required>
                <div className="relative">
                  <UserIcon size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Ahmet Yilmaz"
                    className="input-field pl-10"
                    autoComplete="name"
                  />
                </div>
              </FieldWrapper>

              <FieldWrapper label="Email Address" required>
                <div className="relative">
                  <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="input-field pl-10"
                    autoComplete="email"
                  />
                </div>
              </FieldWrapper>

              <FieldWrapper label="Password — min. 8 chars, 1 uppercase, 1 digit" required>
                <div className="relative">
                  <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                  <input
                    type={showPass ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="input-field pl-10 pr-11"
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass((v) => !v)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
                    aria-label={showPass ? "Hide password" : "Show password"}
                  >
                    {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                {/* Inline strength cues */}
                {password.length > 0 && (
                  <div className="flex gap-3 mt-2">
                    {[
                      { ok: password.length >= 8,      text: "8+ chars"   },
                      { ok: /[A-Z]/.test(password),    text: "Uppercase"  },
                      { ok: /[0-9]/.test(password),    text: "Number"     },
                    ].map(({ ok, text }) => (
                      <span key={text} className={`flex items-center gap-1 text-[11px] ${ok ? "text-accent" : "text-text-muted"}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${ok ? "bg-accent" : "bg-border"}`} />
                        {text}
                      </span>
                    ))}
                  </div>
                )}
              </FieldWrapper>

              <button
                onClick={() => setStep(2)}
                disabled={!canAdvanceStep1}
                className="btn-primary w-full justify-center mt-2"
              >
                Continue to Biometrics <ArrowRight size={16} />
              </button>
            </div>
          )}

          {/* ── STEP 2: Biometric Profile ────────────────────────────────── */}
          {step === 2 && (
            <div className="space-y-4 animate-slide-up">

              <div className="grid grid-cols-2 gap-3">
                <FieldWrapper label="Gender" required>
                  <select
                    className="select-field"
                    value={gender}
                    onChange={(e) => setGender(e.target.value)}
                  >
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                    <option value="other">Other</option>
                  </select>
                </FieldWrapper>

                <FieldWrapper label="Birth Year" required>
                  <div className="relative">
                    <Calendar size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                    <input
                      type="number"
                      value={birthYear}
                      onChange={(e) => setBirthYear(e.target.value)}
                      placeholder="1998"
                      min={1930}
                      max={new Date().getFullYear() - 10}
                      className="input-field pl-10"
                    />
                  </div>
                </FieldWrapper>
              </div>

              <FieldWrapper label="Height (cm)" required>
                <div className="relative">
                  <Ruler size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                  <input
                    type="number"
                    value={heightCm}
                    onChange={(e) => setHeightCm(e.target.value)}
                    placeholder="175"
                    className="input-field pl-10"
                  />
                </div>
              </FieldWrapper>

              <div className="grid grid-cols-2 gap-3">
                <FieldWrapper label="Current Weight (kg)" required>
                  <div className="relative">
                    <Weight size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                    <input
                      type="number"
                      value={currentWeight}
                      onChange={(e) => setCurrentWeight(e.target.value)}
                      placeholder="80"
                      className="input-field pl-10"
                    />
                  </div>
                </FieldWrapper>

                <FieldWrapper label="Target Weight (kg)" required>
                  <div className="relative">
                    <Target size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                    <input
                      type="number"
                      value={targetWeight}
                      onChange={(e) => setTargetWeight(e.target.value)}
                      placeholder="72"
                      className="input-field pl-10"
                    />
                  </div>
                </FieldWrapper>
              </div>

              {/* Weight delta warning */}
              {currentWeight && targetWeight && Math.abs(Number(currentWeight) - Number(targetWeight)) > 100 && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-danger/5 border border-danger/20">
                  <AlertTriangle size={14} className="text-danger shrink-0" />
                  <p className="text-xs text-danger">
                    The difference between current and target weight cannot exceed 100 kg. Please enter a realistic goal.
                  </p>
                </div>
              )}

              <FieldWrapper label="Fitness Level" required>
                <select
                  className="select-field"
                  value={fitnessLevel}
                  onChange={(e) => setFitnessLevel(e.target.value)}
                >
                  {FITNESS_LEVELS.map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </FieldWrapper>

              <div className="flex gap-3 mt-2">
                <button onClick={() => setStep(1)} className="btn-ghost flex-1 justify-center">
                  <ArrowLeft size={16} /> Back
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!canAdvanceStep2}
                  className="btn-primary flex-1 justify-center"
                >
                  Continue <ArrowRight size={16} />
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 3: Injury & Goal Matrix ─────────────────────────────── */}
          {step === 3 && (
            <div className="space-y-5 animate-slide-up">

              {/* Primary goal */}
              <FieldWrapper label="Primary Training Goal" required>
                <select
                  className="select-field"
                  value={primaryGoal}
                  onChange={(e) => setPrimaryGoal(e.target.value)}
                >
                  {PRIMARY_GOALS.map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </FieldWrapper>

              {/* Health condition card grid */}
              <div>
                <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-2">
                  Health Conditions <span className="text-text-muted normal-case font-normal">(select all that apply)</span>
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {HEALTH_CONDITIONS.map(({ value, label, desc, icon }) => {
                    const selected = selectedConditions.includes(value);
                    return (
                      <div key={value}>
                        <button
                          type="button"
                          onClick={() => toggleCondition(value)}
                          className={`w-full text-left p-3 rounded-xl border transition-all duration-150 ${
                            selected
                              ? "bg-primary/10 border-primary/40"
                              : "bg-surface border-border hover:border-primary/25"
                          }`}
                        >
                          <div className="flex items-start gap-2.5">
                            <span className="text-base leading-none mt-0.5">{icon}</span>
                            <div className="flex-1 min-w-0">
                              <p className={`text-sm font-medium ${selected ? "text-primary" : "text-text-primary"}`}>
                                {label}
                              </p>
                              <p className="text-[11px] text-text-muted mt-0.5 truncate">{desc}</p>
                            </div>
                            <div className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 mt-0.5 ${
                              selected ? "bg-primary border-primary" : "border-border"
                            }`}>
                              {selected && <Check size={10} className="text-white" strokeWidth={3} />}
                            </div>
                          </div>
                        </button>

                        {/* Inline severity selector when the condition is selected */}
                        {selected && (
                          <div className="flex gap-1.5 mt-1.5 px-1">
                            {SEVERITY_OPTIONS.map((sev) => (
                              <button
                                key={sev}
                                type="button"
                                onClick={() => setSeverity(value, sev)}
                                className={`flex-1 py-1 rounded-lg text-[10px] font-semibold uppercase tracking-wide transition-colors ${
                                  severityMap[value] === sev
                                    ? sev === "mild"     ? "bg-accent/20 text-accent border border-accent/40"
                                    : sev === "moderate" ? "bg-warning/20 text-warning border border-warning/40"
                                    :                      "bg-danger/20 text-danger border border-danger/40"
                                    : "bg-surface text-text-muted border border-border"
                                }`}
                              >
                                {sev}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Biomechanical Consent & Data Protection Box */}
              <div className={`p-4 rounded-xl border transition-colors ${
                consentGiven ? "bg-accent/5 border-accent/30" : "bg-surface border-border"
              }`}>
                <label className="flex items-start gap-3 cursor-pointer">
                  <div
                    onClick={() => setConsentGiven((v) => !v)}
                    className={`w-5 h-5 rounded border flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
                      consentGiven ? "bg-accent border-accent" : "border-border bg-surface"
                    }`}
                  >
                    {consentGiven && <Check size={12} className="text-base" strokeWidth={3} />}
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-text-primary mb-1 flex items-center gap-1.5">
                      <ShieldCheck size={13} className={consentGiven ? "text-accent" : "text-text-muted"} />
                      Biomechanical Consent &amp; Data Protection
                    </p>
                    <p className="text-[11px] text-text-secondary leading-relaxed">
                      I consent to the secure processing and storage of my posture photographs
                      and biomechanical health metrics strictly within the scope of applicable
                      data protection frameworks (GDPR / KVKK). I acknowledge that this data
                      is used exclusively to personalise my fitness programming within AuraFit AI
                      and will not be shared with third parties without my explicit authorisation.
                    </p>
                  </div>
                </label>
              </div>

              <div className="flex gap-3">
                <button onClick={() => setStep(2)} className="btn-ghost flex-1 justify-center">
                  <ArrowLeft size={16} /> Back
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={loading || !consentGiven}
                  className="btn-primary flex-1 justify-center"
                >
                  {loading ? (
                    <span className="flex items-center gap-2">
                      <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      Creating Account…
                    </span>
                  ) : (
                    <span className="flex items-center gap-2">
                      Complete Registration <Check size={16} />
                    </span>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>

        <p className="text-center text-sm text-text-secondary mt-6">
          Already have an account?{" "}
          <Link to="/login" className="text-primary font-semibold hover:text-primary-hover transition-colors">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
