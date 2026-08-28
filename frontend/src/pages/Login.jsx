/**
 * Login.jsx — AuraFit AI Authentication Engine
 *
 * Layout: Full-screen split panel. Left side (hidden on mobile) renders the
 * AuraFit AI brand hero with animated metric cards. Right side hosts the
 * secure credential form. On successful authentication the user is routed
 * to /posture; errors are surfaced via react-hot-toast and an in-form error banner.
 *
 * Auth flow:
 *   POST /auth/login  →  stores JWT in localStorage via authService  →
 *   refreshUser() hydrates the global AuthContext  →  navigate("/posture")
 */

import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import toast from "react-hot-toast";
import {
  Activity,
  Mail,
  Lock,
  ArrowRight,
  Eye,
  EyeOff,
  ShieldCheck,
  Zap,
  TrendingUp,
  ScanFace,
  AlertCircle,
} from "lucide-react";

import { useAuth } from "../hooks/useAuth";
import api from "../services/api";

// ─── Hero feature list rendered on the left brand panel ──────────────────────
const HERO_FEATURES = [
  {
    icon: ScanFace,
    label: "AI Posture Analysis",
    desc: "MediaPipe 33-landmark skeletal mapping",
  },
  {
    icon: Zap,
    label: "GPT-4o Workout Engine",
    desc: "Injury-aware personalised programming",
  },
  {
    icon: TrendingUp,
    label: "Monthly Progress Tracking",
    desc: "Quantified biomechanical delta reports",
  },
  {
    icon: ShieldCheck,
    label: "GDPR-Aligned Data Handling",
    desc: "Your biometric data stays encrypted",
  },
];

export default function Login() {
  const navigate = useNavigate();
  const { setUser } = useAuth();

  // ── Form state ──────────────────────────────────────────────────────────────
  const [email, setEmail]         = useState("");
  const [password, setPassword]   = useState("");
  const [showPass, setShowPass]   = useState(false);
  const [loading, setLoading]     = useState(false);
  const [errorMessage, setErrorMessage] = useState(""); // Local error state for UI banner

  // ── Submission handler ──────────────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage(""); // Clear previous error messages

    if (!email.trim() || !password) {
      const msg = "Please enter both your email address and password.";
      setErrorMessage(msg);
      toast.error(msg);
      return;
    }

    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      localStorage.setItem("fitcore_token", data.access_token);

      // Hydrate global AuthContext state with user data returned from backend
      if (setUser) {
        setUser(data.user);
      }

      toast.success(`Welcome back, ${data.user?.full_name?.split(" ")[0] || "Athlete"}!`);
      navigate("/posture");
    } catch (err) {
   const detail = err.response?.data?.detail;
      const message =
        (typeof detail === "object" ? detail?.message : detail) ||
        err.message ||
        "Invalid email or password. Please check your credentials.";

      setErrorMessage(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen flex bg-base">

      {/* ── Left: Brand hero panel (desktop only) ─────────────────────────── */}
      <div className="hidden lg:flex flex-col justify-between w-[52%] bg-surface border-r border-border p-12 relative overflow-hidden">

        {/* Ambient glow orbs */}
        <div className="absolute top-[-120px] left-[-80px] w-96 h-96 rounded-full bg-primary/10 blur-3xl pointer-events-none" />
        <div className="absolute bottom-[-80px] right-[-60px] w-72 h-72 rounded-full bg-accent/8 blur-3xl pointer-events-none" />

        {/* Wordmark */}
        <div className="flex items-center gap-3 relative z-10">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-glow-primary">
            <Activity size={20} className="text-white" strokeWidth={2.5} />
          </div>
          <span className="font-display font-bold text-2xl tracking-tight">
            AuraFit <span className="text-primary">AI</span>
          </span>
        </div>

        {/* Hero headline */}
        <div className="relative z-10 space-y-6">
          <div>
            <h1 className="font-display text-4xl font-bold text-text-primary leading-tight">
              Intelligent Fitness,<br />
              <span className="text-gradient-primary">Engineered for You.</span>
            </h1>
            <p className="text-text-secondary mt-4 text-base leading-relaxed max-w-sm">
              AuraFit AI fuses computer vision, large language models, and exercise
              science to deliver a truly personalised training experience.
            </p>
          </div>

          {/* Feature list */}
          <ul className="space-y-4">
            {HERO_FEATURES.map(({ icon: Icon, label, desc }) => (
              <li key={label} className="flex items-start gap-4">
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Icon size={17} className="text-primary" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-text-primary">{label}</p>
                  <p className="text-xs text-text-muted mt-0.5">{desc}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* Footer tagline */}
        <p className="text-xs text-text-muted relative z-10">
          Istanbul Okan University · Software Engineering Graduation Project · 2027
        </p>
      </div>

      {/* ── Right: Login form panel ───────────────────────────────────────── */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12">

        {/* Mobile-only wordmark */}
        <div className="flex lg:hidden items-center gap-2 mb-8">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center">
            <Activity size={18} className="text-white" strokeWidth={2.5} />
          </div>
          <span className="font-display font-bold text-xl">
            AuraFit <span className="text-primary">AI</span>
          </span>
        </div>

        <div className="w-full max-w-sm animate-slide-up">

          {/* Heading */}
          <h2 className="font-display text-2xl font-bold text-text-primary mb-1">
            Sign In
          </h2>
          <p className="text-sm text-text-secondary mb-6">
            Access your personalised fitness command centre.
          </p>

          {/* Dynamic Error Alert Banner */}
          {errorMessage && (
            <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 flex items-start gap-2.5 animate-fadeIn">
              <AlertCircle size={18} className="shrink-0 mt-0.5" />
              <p className="text-xs font-medium leading-relaxed">{errorMessage}</p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} noValidate className="space-y-4">

            {/* Email */}
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1.5 uppercase tracking-wide">
                Email Address
              </label>
              <div className="relative">
                <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                <input
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="input-field pl-10"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1.5 uppercase tracking-wide">
                Password
              </label>
              <div className="relative">
                <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" />
                <input
                  type={showPass ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="input-field pl-10 pr-11"
                />
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
                  aria-label={showPass ? "Hide password" : "Show password"}
                >
                  {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full justify-center mt-2"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Authenticating…
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  Sign In <ArrowRight size={16} />
                </span>
              )}
            </button>
          </form>

          {/* Security note */}
          <div className="flex items-center gap-2 mt-6 p-3 rounded-xl bg-accent/5 border border-accent/15">
            <ShieldCheck size={14} className="text-accent shrink-0" />
            <p className="text-[11px] text-text-muted leading-relaxed">
              All sessions are secured with RS256-signed JWT tokens. Credentials
              are never stored in plain text.
            </p>
          </div>

          {/* Register link */}
          <p className="text-center text-sm text-text-secondary mt-8">
            New to AuraFit AI?{" "}
            <Link
              to="/register"
              className="text-primary font-semibold hover:text-primary-hover transition-colors"
            >
              Create your account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}