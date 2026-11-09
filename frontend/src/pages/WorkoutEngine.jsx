import React, { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import {
  Dumbbell, Sparkles, ChevronDown, ChevronRight, Clock,
  RotateCcw, Shield, Play, Zap, Calendar,
} from "lucide-react";
import toast from "react-hot-toast";
import Topbar from "../components/layout/Topbar";
import Spinner from "../components/ui/Spinner";
import EmptyState from "../components/ui/EmptyState";
import { workoutService } from "../services/workoutService";
import { useAuth } from "../hooks/useAuth";
import { formatGoal } from "../utils/format";

const EQUIP_OPTIONS = [
  "body weight", "dumbbell", "barbell", "cable",
  "machine", "resistance band", "kettlebell",
];

const DAY_TYPE_STYLE = {
  workout:         { cls: "badge-primary",  label: "Workout" },
  rest:            { cls: "badge-muted",    label: "Rest" },
  active_recovery: { cls: "badge-accent",   label: "Recovery" },
  cardio:          { cls: "badge-warning",  label: "Cardio" },
};

function ExerciseRow({ ex, idx }) {
  const [open, setOpen] = useState(false);
  const exerciseName = ex.exercise_name || ex.name || "Exercise";

  return (
    <div className="rounded-xl bg-surface border border-border overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-card/50 transition-colors text-left"
      >
        <span className="w-6 h-6 rounded-full bg-primary/15 flex items-center justify-center text-primary text-xs font-semibold shrink-0">
          {idx}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-text-primary truncate">{exerciseName}</p>
          <p className="text-xs text-text-muted capitalize">
            {ex.body_part || "Full Body"} · {ex.equipment || "Body Weight"}
          </p>
        </div>
        <div className="hidden sm:flex items-center gap-4 text-xs text-text-secondary mr-2">
          <span className="flex items-center gap-1">
            <Play size={11} className="text-primary" /> {ex.sets} sets
          </span>
          <span className="flex items-center gap-1">
            <Zap size={11} className="text-accent" /> {ex.reps} reps
          </span>
          <span className="flex items-center gap-1">
            <Clock size={11} className="text-text-muted" /> {ex.rest_seconds || 60}s rest
          </span>
        </div>
        {open ? <ChevronDown size={15} className="text-text-muted" /> : <ChevronRight size={15} className="text-text-muted" />}
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3 animate-fade-in">
          <div className="sm:hidden flex gap-3 text-xs text-text-secondary pt-1">
            <span className="flex items-center gap-1"><Play size={11} className="text-primary" />{ex.sets} sets</span>
            <span className="flex items-center gap-1"><Zap size={11} className="text-accent" />{ex.reps} reps</span>
            <span className="flex items-center gap-1"><Clock size={11} className="text-text-muted" />{ex.rest_seconds || 60}s rest</span>
          </div>
          {ex.ai_notes && (
            <div className="flex items-start gap-2 p-3 rounded-lg bg-primary/5 border border-primary/15 mt-2">
              <Shield size={13} className="text-primary mt-0.5 shrink-0" />
              <p className="text-xs text-text-secondary">{ex.ai_notes}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DayCard({ day }) {
  const [open, setOpen] = useState(false);
  const typeStyle = DAY_TYPE_STYLE[day.day_type] || DAY_TYPE_STYLE.workout;
  const isRest = day.day_type === "rest";

  const exerciseList = day.exercises || day._exercises || [];

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => !isRest && setOpen((o) => !o)}
        className={`w-full flex items-center justify-between px-5 py-4 ${!isRest ? "hover:bg-card-hover transition-colors" : ""}`}
      >
        <div className="flex items-center gap-3">
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold font-display ${
            isRest ? "bg-border text-text-muted" : "bg-primary/10 text-primary"
          }`}>
            {day.day_number}
          </div>
          <div className="text-left">
            <p className="text-sm font-semibold text-text-primary">{day.day_label || `Day ${day.day_number}`}</p>
            <p className="text-xs text-text-muted">{day.muscle_focus || "Rest & Recovery"}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className={`badge ${typeStyle.cls}`}>{typeStyle.label}</span>
          {!isRest && (exerciseList.length > 0) && (
            <span className="text-xs text-text-muted hidden sm:block">{exerciseList.length} exercises</span>
          )}
          {!isRest && (open
            ? <ChevronDown size={16} className="text-text-muted" />
            : <ChevronRight size={16} className="text-text-muted" />
          )}
        </div>
      </button>

      {open && exerciseList.length > 0 && (
        <div className="px-5 pb-5 space-y-2 animate-fade-in">
          <div className="divider mb-4" />
          {exerciseList.map((ex, i) => (
            <ExerciseRow key={i} ex={ex} idx={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function WeekSection({ week, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const workoutDays = week.days.filter((d) => d.day_type !== "rest").length;

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between mb-3 group"
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Calendar size={16} className="text-primary" />
            <span className="font-display font-semibold text-text-primary">
              Week {week.week_number}
            </span>
          </div>
          <span className="text-xs text-text-muted">{workoutDays} training days</span>
        </div>
        {open ? <ChevronDown size={16} className="text-text-muted" /> : <ChevronRight size={16} className="text-text-muted" />}
      </button>

      {open && (
        <div className="space-y-2 animate-fade-in">
          {week.days.map((day, i) => (
            <DayCard key={i} day={day} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function WorkoutEngine() {
  const { user } = useAuth();
  const { onMenuClick } = useOutletContext() || {};
  const [generating, setGenerating] = useState(false);
  const [fetchingActive, setFetchingActive] = useState(true);
  const [plan, setPlan] = useState(null);
  const [options, setOptions] = useState({
    available_days_per_week: 3,
    program_duration_weeks: 8,
    available_equipment: ["dumbbell", "body weight"],
    preferred_provider: "auto",
  });

  // User-specific storage key to prevent cross-account plan leaking
  const userPlanStorageKey = user?.id ? `aurafit_active_plan_${user.id}` : null;

  // Load existing active plan on page mount or user change
  useEffect(() => {
    async function loadActivePlan() {
      setFetchingActive(true);
      setPlan(null); // Reset plan state on user switch

      if (!user?.id) {
        setFetchingActive(false);
        return;
      }

      try {
        let activeData = null;
        if (workoutService.getActivePlan) {
          activeData = await workoutService.getActivePlan();
        }

        // User-specific local storage check
        if (!activeData && userPlanStorageKey) {
          const cached = localStorage.getItem(userPlanStorageKey);
          if (cached) {
            activeData = JSON.parse(cached);
          }
        }

        if (activeData) {
          setPlan(activeData);
        }
      } catch (err) {
        if (userPlanStorageKey) {
          const cached = localStorage.getItem(userPlanStorageKey);
          if (cached) {
            try {
              setPlan(JSON.parse(cached));
            } catch (e) {
              /* ignore parse error */
            }
          }
        }
      } finally {
        setFetchingActive(false);
      }
    }

    loadActivePlan();
  }, [user?.id, userPlanStorageKey]);

  const toggleEquip = (e) => {
    setOptions((o) => ({
      ...o,
      available_equipment: o.available_equipment.includes(e)
        ? o.available_equipment.filter((x) => x !== e)
        : [...o.available_equipment, e],
    }));
  };

  const generate = async () => {
    setGenerating(true);
    setPlan(null);
    try {
      const data = await workoutService.generatePlan(options);
      setPlan(data);
      if (userPlanStorageKey) {
        localStorage.setItem(userPlanStorageKey, JSON.stringify(data));
      }
      toast.success("Your AI workout plan is ready!");
    } catch (err) {
      toast.error(err.message || "Failed to generate plan.");
    } finally {
      setGenerating(false);
    }
  };

  const resetPlan = () => {
    setPlan(null);
    if (userPlanStorageKey) {
      localStorage.removeItem(userPlanStorageKey);
    }
  };

  const weeks = plan?.raw_plan?.weeks || [];

  return (
    <>
      <Topbar
        title="AI Workout Engine"
        subtitle="Generate a personalized multi-week training program tailored to your profile"
        onMenuClick={onMenuClick}
        actions={
          plan && (
            <button onClick={resetPlan} className="btn-ghost text-xs">
              <RotateCcw size={14} /> New Plan
            </button>
          )
        }
      />

      <main className="p-4 lg:p-8 max-w-5xl mx-auto space-y-6">
        {fetchingActive ? (
          <div className="flex justify-center items-center py-20">
            <Spinner size={24} label="Loading your active training program..." />
          </div>
        ) : (
          <>
            {/* Generation config */}
            {!plan && (
              <div className="card p-6 space-y-5 animate-fade-in">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
                    <Sparkles size={18} className="text-primary" />
                  </div>
                  <div>
                    <h2 className="section-title">Configure Your Program</h2>
                    <p className="section-subtitle">
                      The AI will automatically account for your registered health conditions
                      and fitness level.
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: "Goal", value: formatGoal(user?.primary_goal) },
                    { label: "Level", value: user?.fitness_level || "—" },
                    { label: "Conditions", value: (user?.health_conditions?.filter((c) => c.is_active).length || 0) + " active" },
                    { label: "BMI", value: user?.current_weight_kg && user?.height_cm ? (user.current_weight_kg / (user.height_cm / 100) ** 2).toFixed(1) : "—" },
                  ].map(({ label, value }) => (
                    <div key={label} className="p-3 rounded-xl bg-surface border border-border">
                      <p className="text-[11px] text-text-muted uppercase tracking-wide">{label}</p>
                      <p className="text-sm font-medium text-text-primary capitalize mt-0.5">{value}</p>
                    </div>
                  ))}
                </div>

                <div className="divider" />

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                      Training days per week: <span className="text-primary">{options.available_days_per_week}</span>
                    </label>
                    <input type="range" min={2} max={6} step={1}
                      value={options.available_days_per_week}
                      onChange={(e) => setOptions({ ...options, available_days_per_week: Number(e.target.value) })}
                      className="w-full accent-primary" />
                    <div className="flex justify-between text-[11px] text-text-muted mt-1">
                      <span>2 days</span><span>6 days</span>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                      Program duration: <span className="text-primary">{options.program_duration_weeks} weeks</span>
                    </label>
                    <input type="range" min={4} max={24} step={4}
                      value={options.program_duration_weeks}
                      onChange={(e) => setOptions({ ...options, program_duration_weeks: Number(e.target.value) })}
                      className="w-full accent-primary" />
                    <div className="flex justify-between text-[11px] text-text-muted mt-1">
                      <span>4 wks</span><span>24 wks</span>
                    </div>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-text-secondary mb-2 block">Available Equipment</label>
                  <div className="flex flex-wrap gap-2">
                    {EQUIP_OPTIONS.map((e) => {
                      const active = options.available_equipment.includes(e);
                      return (
                        <button key={e} onClick={() => toggleEquip(e)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                            active ? "bg-primary/15 border-primary/40 text-primary" : "bg-surface border-border text-text-muted hover:border-primary/30"
                          }`}
                        >
                          {e}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <button onClick={generate} disabled={generating} className="btn-primary w-full justify-center">
                  {generating ? <Spinner size={16} label="AI is building your program..." /> : <><Sparkles size={16} /> Generate My Program</>}
                </button>
              </div>
            )}

            {/* Plan overview banner */}
            {plan && (
              <div className="card-glow p-5 flex flex-wrap items-center gap-6 animate-fade-in">
                <div className="flex-1 min-w-0">
                  <h2 className="font-display text-xl font-semibold text-text-primary truncate">
                    {plan.db_plan_payload?.plan_name || "Your AI Program"}
                  </h2>
                  <p className="text-sm text-text-secondary mt-1">{plan.db_plan_payload?.ai_reasoning}</p>
                </div>
                <div className="flex flex-wrap gap-4 text-center">
                  {[
                    { label: "Weeks", value: plan.db_plan_payload?.duration_weeks },
                    { label: "Days/Week", value: plan.db_plan_payload?.sessions_per_week },
                    { label: "Est. Months", value: plan.db_plan_payload?.estimated_months },
                    { label: "Difficulty", value: plan.db_plan_payload?.difficulty },
                  ].map(({ label, value }) => (
                    <div key={label} className="min-w-[70px]">
                      <p className="font-display text-2xl font-bold text-primary capitalize">{value ?? "—"}</p>
                      <p className="text-[11px] text-text-muted uppercase tracking-wide">{label}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Weeks */}
            {plan && weeks.length > 0 && (
              <div className="space-y-4">
                {weeks.map((week, i) => (
                  <WeekSection key={week.week_number} week={week} defaultOpen={i === 0} />
                ))}
              </div>
            )}

            {/* Empty state */}
            {!plan && !generating && (
              <EmptyState
                icon={Dumbbell}
                title="No program generated yet"
                description="Configure your options above and click Generate to let the AI build your personalized plan."
              />
            )}
          </>
        )}
      </main>
    </>
  );
}