"""
progress_service.py — Monthly Posture Progress Comparison Service

Functionality:
  1. Fetches user's baseline (Month 1) posture metrics.
  2. Analyzes the new photo using cv_service.
  3. Calculates metric changes (deltas).
  4. Sends metrics to LLM to generate an English progress report.
  5. Returns payload ready to be saved into the comparison_delta JSONB field.

Usage (from main.py):
    from progress_service import compare_posture, CompareInput, CompareOutput
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from ai_service import generate_posture_comparison_report

try:
    from openai import AsyncOpenAI
    _OPENAI_OK = True
except ImportError:
    _OPENAI_OK = False

try:
    from anthropic import AsyncAnthropic
    _ANTHROPIC_OK = True
except ImportError:
    _ANTHROPIC_OK = False

from config import get_settings
from cv_service import analyze_posture, PostureResult

settings = get_settings()

_PROMPT_PATH = Path(__file__).parent / "prompts" / "progress_report.txt"
_CACHED_PROMPT: Optional[str] = None


def _load_report_prompt() -> str:
    global _CACHED_PROMPT
    if _CACHED_PROMPT is None:
        _CACHED_PROMPT = (
            _PROMPT_PATH.read_text(encoding="utf-8")
            if _PROMPT_PATH.exists()
            else (
                "Compare the user's two-month posture metrics. "
                "Respond strictly in JSON format in English."
            )
        )
    return _CACHED_PROMPT


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class BaselineMetrics:
    """
    Posture metrics belonging to Month 1 (or prior baseline measurement).
    Populated from the body_measurements JSONB column in photo_analyses table.
    """
    posture_score: float
    month_number: int                            # Target month (1 = baseline)
    photo_angle: str = "front"
    shoulder_tilt_deg: Optional[float] = None
    hip_tilt_deg: Optional[float] = None
    spine_lateral_dev_deg: Optional[float] = None
    head_forward_deg: Optional[float] = None
    torso_lean_deg: Optional[float] = None
    shoulder_width_ratio: Optional[float] = None


@dataclass
class CompareInput:
    """Request payload coming from POST /analysis/posture/compare endpoint."""
    user_id: str
    user_name: str
    # Newly uploaded photo (bytes)
    new_photo_bytes: bytes
    photo_angle: str              # "front" | "back" | "left" | "right"
    new_month_number: int         # Target month (2, 3, 4...)
    # Baseline: Metrics fetched from DB for previous month
    baseline: BaselineMetrics
    preferred_provider: str = "auto"


@dataclass
class MetricDelta:
    """Before-and-after difference for a single posture metric."""
    metric_name: str
    baseline_value: Optional[float]
    new_value: Optional[float]
    delta: Optional[float]          # new - baseline (negative = improvement for most angles)
    change_pct: Optional[float]     # Percentage change
    improved: Optional[bool]        # True = posture improvement

    @classmethod
    def compute(
        cls,
        name: str,
        baseline: Optional[float],
        new: Optional[float],
        lower_is_better: bool = True,
    ) -> "MetricDelta":
        """
        lower_is_better=True: angle decrease means improved=True (shoulder tilt, head forward, etc.)
        lower_is_better=False: value increase means improved=True (such as posture score)
        """
        if baseline is None or new is None:
            return cls(name, baseline, new, None, None, None)

        delta = round(new - baseline, 3)
        change_pct = round((delta / baseline) * 100, 1) if baseline != 0 else None
        improved = (delta < 0) if lower_is_better else (delta > 0)
        return cls(name, round(baseline, 3), round(new, 3), delta, change_pct, improved)


@dataclass
class ProgressDelta:
    """Comparison results across all posture metrics."""
    posture_score:      MetricDelta
    shoulder_tilt:      MetricDelta
    hip_tilt:           MetricDelta
    spine_lateral:      MetricDelta
    head_forward:       MetricDelta
    torso_lean:         MetricDelta
    shoulder_width_ratio: MetricDelta

    def improved_count(self) -> int:
        return sum(
            1 for m in self._all() if m.improved is True
        )

    def worsened_count(self) -> int:
        return sum(
            1 for m in self._all() if m.improved is False
        )

    def _all(self) -> list[MetricDelta]:
        return [
            self.posture_score, self.shoulder_tilt, self.hip_tilt,
            self.spine_lateral, self.head_forward, self.torso_lean,
            self.shoulder_width_ratio,
        ]

    def to_dict(self) -> dict:
        """Dictionary representation to be written to photo_analyses.comparison_delta JSONB column."""
        return {
            m.metric_name: {
                "baseline": m.baseline_value,
                "new":      m.new_value,
                "delta":    m.delta,
                "change_pct": m.change_pct,
                "improved": m.improved,
            }
            for m in self._all()
            if m.baseline_value is not None or m.new_value is not None
        }


@dataclass
class CompareOutput:
    """Return type for compare_posture()."""
    success: bool
    new_posture_score: float
    delta: ProgressDelta
    # Parsed LLM-generated report in English
    report: dict
    ai_report: Optional[dict] = field(default_factory=dict)
    # Raw payload to be saved into database
    new_analysis_db_payload: dict = field(default_factory=dict)
    error_message: Optional[str] = None

    def summary_text(self) -> str:
        """
        Simple single-paragraph summary for Frontend.
        Manually constructs deltas if LLM report is unavailable.
        """
        if self.report.get("overall_verdict"):
            return self.report["overall_verdict"]
        d = self.delta
        parts = []
        if d.posture_score.delta is not None:
            trend = "increased" if d.posture_score.delta > 0 else "decreased"
            parts.append(f"Your posture score {trend} by {abs(d.posture_score.delta):.1f} points.")
        if d.shoulder_tilt.improved is True:
            parts.append(f"Shoulder alignment improved by {abs(d.shoulder_tilt.delta):.1f}°.")
        return " ".join(parts) or "Analysis completed successfully."


# ─── Delta Calculator ─────────────────────────────────────────────────────────

def _compute_delta(baseline: BaselineMetrics, new_result: PostureResult) -> ProgressDelta:
    """Calculates differences between two posture analyses."""
    nm = new_result.metrics
    return ProgressDelta(
        posture_score=MetricDelta.compute(
            "posture_score", baseline.posture_score, new_result.posture_score,
            lower_is_better=False,          # Score increase indicates improvement
        ),
        shoulder_tilt=MetricDelta.compute(
            "shoulder_tilt_deg", baseline.shoulder_tilt_deg, nm.shoulder_tilt_deg,
        ),
        hip_tilt=MetricDelta.compute(
            "hip_tilt_deg", baseline.hip_tilt_deg, nm.hip_tilt_deg,
        ),
        spine_lateral=MetricDelta.compute(
            "spine_lateral_dev_deg", baseline.spine_lateral_dev_deg, nm.spine_lateral_dev_deg,
        ),
        head_forward=MetricDelta.compute(
            "head_forward_deg", baseline.head_forward_deg, nm.head_forward_deg,
        ),
        torso_lean=MetricDelta.compute(
            "torso_lean_deg", baseline.torso_lean_deg, nm.torso_lean_deg,
        ),
        shoulder_width_ratio=MetricDelta.compute(
            "shoulder_width_ratio", baseline.shoulder_width_ratio, nm.shoulder_width_ratio,
            lower_is_better=False,
        ),
    )


# ─── LLM Report Prompt Builder ────────────────────────────────────────────────

def _build_report_user_prompt(
    user_name: str,
    baseline: BaselineMetrics,
    new_result: PostureResult,
    delta: ProgressDelta,
    month_number: int,
) -> str:
    """Converts structured comparison data into a formatted prompt string for LLM."""

    def fmt(val: Optional[float]) -> str:
        return f"{val:.2f}" if val is not None else "not measured"

    def fmt_delta(m: MetricDelta) -> str:
        if m.delta is None:
            return "cannot compare (missing data)"
        sign = "+" if m.delta > 0 else ""
        trend = "✓ improved" if m.improved else ("✗ worsened" if m.improved is False else "—")
        return f"{fmt(m.baseline_value)} → {fmt(m.new_value)} (Δ {sign}{m.delta:.2f}, {m.change_pct:+.1f}%) {trend}"

    nm = new_result.metrics
    lines = [
        f"## User: {user_name}",
        f"## Comparison: Baseline (Month {baseline.month_number}) → Current (Month {month_number})",
        f"## Photo Angle: {new_result.photo_angle}",
        "",
        "### Posture Score (0-100)",
        f"  {fmt_delta(delta.posture_score)}",
        "",
        "### Shoulder Tilt (°, lower = better)",
        f"  {fmt_delta(delta.shoulder_tilt)}",
        "",
        "### Hip Tilt (°, lower = better)",
        f"  {fmt_delta(delta.hip_tilt)}",
        "",
        "### Spine Lateral Deviation (°, lower = better)",
        f"  {fmt_delta(delta.spine_lateral)}",
        "",
        "### Head Forward Lean (°, lower = better)",
        f"  {fmt_delta(delta.head_forward)}",
        "",
        "### Torso Lean (°, lower = better)",
        f"  {fmt_delta(delta.torso_lean)}",
        "",
        f"### Summary: {delta.improved_count()} metrics improved, {delta.worsened_count()} metrics worsened.",
        "",
        "Warnings in new measurement:",
    ]
    for w in (nm.warnings or []):
        lines.append(f"  - {w}")
    if not nm.warnings:
        lines.append("  (none)")

    lines.append("\nBased on the above data, write a progress report strictly in English in the JSON format specified in the system prompt.")
    return "\n".join(lines)


# ─── JSON Extraction Helper ───────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """Extracts and parses JSON block from LLM response text."""
    # Markdown code block check
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # First { to last }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start: end + 1])
    raise ValueError(f"LLM did not return valid JSON. Raw output: {text[:300]}")


# ─── LLM Service Calls ────────────────────────────────────────────────────────

async def _call_openai_report(system: str, user: str) -> str:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.4,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


async def _call_anthropic_report(system: str, user: str) -> str:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model="claude-sonnet-4-6",   # High-quality model for progress report generation
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0.4,
    )
    return resp.content[0].text


# ─── Main Comparison Function ─────────────────────────────────────────────────
async def compare_posture(data: CompareInput) -> CompareOutput:
    """
    Analyzes the new photo, compares it with baseline, and generates an LLM report.
    """

    # 1. Analyze new photo via CV service
    new_result: PostureResult = analyze_posture(
        data.new_photo_bytes,
        photo_angle=data.photo_angle,
        return_annotated=False,
    )

    if not new_result.success:
        return CompareOutput(
            success=False,
            new_posture_score=0.0,
            delta=_compute_delta(data.baseline, new_result),  # Empty delta
            report={},
            new_analysis_db_payload={},
            error_message=new_result.error_message,
        )

    # 2. Compute deltas
    delta = _compute_delta(data.baseline, new_result)

    # 3. Calculate score change
    baseline_score = getattr(data.baseline, "posture_score", 0.0)
    new_score = new_result.posture_score
    score_change = round(new_score - baseline_score, 1)

    # 4. Generate AI Assessment Report
    # Uses the generate_posture_comparison_report function from ai_service.py
    ai_report_data = await generate_posture_comparison_report(
        baseline_metrics=data.baseline.to_dict() if hasattr(data.baseline, "to_dict") else {},
        new_metrics=new_result.to_db_dict(),
        score_change=score_change,
    )

    # 5. Prepare DB payload (photo_analyses table)
    cv_db = new_result.to_db_dict()
    cv_db["comparison_delta"] = delta.to_dict()   # JSONB column

    # 6. Format formatted metrics mapping for frontend compatibility
    # Ensure keys match: shoulder_tilt_deg, hip_tilt_deg, etc.
    metrics_map = {}
    delta_dict = delta.to_dict() if hasattr(delta, "to_dict") else {}
    for key, val in delta_dict.items():
        metrics_map[key] = {
            "baseline": getattr(data.baseline, key, 0.0),
            "new": getattr(new_result, key, 0.0),
            "delta": val,
        }

    # Construct structured payload for frontend
    frontend_payload = {
        "scores": {
            "baseline_score": baseline_score,
            "new_score": new_score,
            "score_change": score_change,
        },
        "metrics": metrics_map,
        "ai_report": ai_report_data,
        "improved_count": sum(1 for v in delta_dict.values() if isinstance(v, (int, float)) and v < 0),
        "worsened_count": sum(1 for v in delta_dict.values() if isinstance(v, (int, float)) and v > 0),
        "summary": ai_report_data.get("overall_verdict", ""),
    }

    return CompareOutput(
        success=True,
        new_posture_score=new_score,
        delta=delta,
        report=frontend_payload,
        ai_report=ai_report_data or {},
        new_analysis_db_payload={**cv_db}
    )