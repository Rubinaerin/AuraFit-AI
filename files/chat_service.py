"""
chat_service.py — AI Fitness Coach Chatbot Service with Memory

Memory Mechanism:
  Conversation history is stored in the PostgreSQL chat_messages table.
  On each request, main.py retrieves the latest MAX_HISTORY messages from DB,
  populates the ChatInput.history list, and calls this service.
  The LLM sees full context on every turn — no external vector DB required.

Usage (from main.py):
    from chat_service import chat_with_coach, ChatInput, ChatOutput
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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

settings = get_settings()

_PROMPT_PATH = Path(__file__).parent / "prompts" / "coach_persona.txt"
_CACHED_PROMPT: Optional[str] = None

MAX_HISTORY = 20   # Maximum historical messages passed to LLM


def _load_coach_prompt() -> str:
    global _CACHED_PROMPT
    if _CACHED_PROMPT is None:
        _CACHED_PROMPT = (
            _PROMPT_PATH.read_text(encoding="utf-8")
            if _PROMPT_PATH.exists()
            else "You are FitCoach AI, an expert, empathetic personal trainer. You have full awareness of the user's generated AI Workout Plan and profile."
        )
    return _CACHED_PROMPT


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class HealthConditionCtx:
    condition_type: str       # lumbar_hernia | knee_injury | shoulder_injury ...
    severity: str             # mild | moderate | severe
    affected_region: Optional[str] = None


@dataclass
class ActivePlanCtx:
    plan_name: str
    sessions_per_week: int
    primary_goal: str
    current_week: int = 1
    current_week_exercises: list[str] = field(default_factory=list)


@dataclass
class ChatInput:
    user_id: str
    user_name: str
    message: str
    session_id: Optional[str] = None
    health_conditions: list[HealthConditionCtx] = field(default_factory=list)
    active_plan: Optional[ActivePlanCtx] = None
    has_posture_data: bool = False
    history: list[dict] = field(default_factory=list)
    preferred_provider: str = "auto"


@dataclass
class PlanUpdateAction:
    action: str
    old_exercise: Optional[str] = None
    new_exercise: Optional[str] = None
    reason: Optional[str] = None
    sets: Optional[int] = None
    reps: Optional[str] = None
    rest_seconds: Optional[int] = None


@dataclass
class ChatOutput:
    reply: str
    session_id: str
    plan_update: Optional[PlanUpdateAction] = None
    tokens_used: int = 0
    provider_used: str = ""
    _raw_user_message: str = field(default="", repr=False)

    def user_db_row(self) -> dict:
        return {
            "role": "user",
            "content": self._raw_user_message,
            "token_count": None,
            "plan_update_diff": None,
        }

    def assistant_db_row(self) -> dict:
        return {
            "role": "assistant",
            "content": self.reply,
            "token_count": self.tokens_used,
            "plan_update_diff": (
                {
                    "action":       self.plan_update.action,
                    "old_exercise": self.plan_update.old_exercise,
                    "new_exercise": self.plan_update.new_exercise,
                    "reason":       self.plan_update.reason,
                }
                if self.plan_update else None
            ),
        }


# ─── System Prompt Builder ───────────────────────────────────────────────────

def _build_system_prompt(data: ChatInput) -> str:
    lines = [
        _load_coach_prompt(),
        "",
        "════════════════════════════════════════",
        "CURRENT USER PROFILE & SYSTEM CONTEXT",
        "════════════════════════════════════════",
        f"Name: {data.user_name}"
    ]

    # Health Condition rules & exercise restrictions
    if data.health_conditions:
        lines.append("\nHealth Conditions ⚠️ — STRICTLY ENFORCE THESE SAFETY RULES:")
        for c in data.health_conditions:
            region = f" ({c.affected_region})" if c.affected_region else ""
            lines.append(f"  • Condition: {c.condition_type}{region} — Severity: {c.severity}")
            
            # Specific restrictions mapping
            if "knee" in c.condition_type.lower():
                lines.append("    CRITICAL INSTRUCTION: Deadlifts, Barbell Squats, Heavy Lunges, and Jump exercises ARE STRICTLY FORBIDDEN due to knee strain. Recommend low-impact alternatives like Glute Bridges, Leg Press (shallow), or Upper Body movements.")
            elif "hernia" in c.condition_type.lower() or "lumbar" in c.condition_type.lower():
                lines.append("    CRITICAL INSTRUCTION: Avoid heavy spinal loading (Barbell Deadlifts, Heavy Overhead Squats).")
    else:
        lines.append("Health Conditions: None")

    if data.has_posture_data:
        lines.append("Posture Analysis Status: Completed.")
    else:
        lines.append("Posture Analysis Status: Not uploaded yet.")

    if data.active_plan:
        p = data.active_plan
        lines += [
            "",
            "Active Workout Program (Generated by AI Workout Engine):",
            f"  • Plan Name: {p.plan_name} | {p.sessions_per_week} days/week | Goal: {p.primary_goal} | Week {p.current_week}",
        ]
        if p.current_week_exercises:
            lines.append("  • Active Exercises in Program: " + ", ".join(p.current_week_exercises))
    
    lines.append("\nSYSTEM GUIDANCE:")
    lines.append("1. You ARE the official FitCoach AI for this platform. You have FULL ACCESS to discuss and explain the user's AI Workout Engine program.")
    lines.append("2. If the user asks why an exercise (like Deadlift) is in their program despite having an injury, EMPATHIZE, admit the AI engine made an oversight, explain why that exercise is unsuitable for their injury, and offer to substitute it immediately.")
    lines.append("3. Always respond in the language used by the user (Turkish if they speak Turkish, English if English).")

    return "\n".join(lines)


# ─── PLAN_UPDATE Parser ───────────────────────────────────────────────────────

_UPDATE_RE = re.compile(r"PLAN_UPDATE:\s*(\{.+?\})", re.DOTALL)


def _parse_plan_update(raw: str) -> tuple[str, Optional[PlanUpdateAction]]:
    m = _UPDATE_RE.search(raw)
    if not m:
        return raw.strip(), None

    clean = raw[: m.start()].strip()
    try:
        d = json.loads(m.group(1))
        return clean, PlanUpdateAction(
            action=d.get("action", "replace_exercise"),
            old_exercise=d.get("old_exercise"),
            new_exercise=d.get("new_exercise"),
            reason=d.get("reason"),
            sets=d.get("sets"),
            reps=str(d.get("reps", "12")),
            rest_seconds=d.get("rest_seconds", 60),
        )
    except (json.JSONDecodeError, KeyError):
        return clean, None


# ─── LLM Calls ───────────────────────────────────────────────────────────────

async def _call_openai(system: str, history: list[dict], message: str) -> tuple[str, int]:
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    msgs = [{"role": "system", "content": system}]
    msgs.extend(history[-MAX_HISTORY:])
    msgs.append({"role": "user", "content": message})
    resp = await client.chat.completions.create(
        model="gpt-4o-mini", messages=msgs, temperature=0.65, max_tokens=600,
    )
    return resp.choices[0].message.content, resp.usage.total_tokens


async def _call_anthropic(system: str, history: list[dict], message: str) -> tuple[str, int]:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    msgs = list(history[-MAX_HISTORY:])
    msgs.append({"role": "user", "content": message})
    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=600,
        system=system, messages=msgs, temperature=0.65,
    )
    return resp.content[0].text, resp.usage.input_tokens + resp.usage.output_tokens


# ─── Main Function ────────────────────────────────────────────────────────────

async def chat_with_coach(data: ChatInput) -> ChatOutput:
    provider = data.preferred_provider
    if provider == "auto":
        if _OPENAI_OK and getattr(settings, "openai_api_key", None):
            provider = "openai"
        elif _ANTHROPIC_OK and getattr(settings, "anthropic_api_key", None):
            provider = "anthropic"
        else:
            raise RuntimeError("No LLM API key found.")

    system = _build_system_prompt(data)
    session_id = data.session_id or str(uuid.uuid4())

    raw, tokens = (
        await _call_openai(system, data.history, data.message)
        if provider == "openai"
        else await _call_anthropic(system, data.history, data.message)
    )

    clean_reply, plan_update = _parse_plan_update(raw)

    out = ChatOutput(
        reply=clean_reply,
        session_id=session_id,
        plan_update=plan_update,
        tokens_used=tokens,
        provider_used=provider,
    )
    out._raw_user_message = data.message
    return out