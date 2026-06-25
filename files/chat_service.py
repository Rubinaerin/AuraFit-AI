"""
chat_service.py — Hafızalı AI Antrenör Chatbot Servisi

Hafıza mekanizması:
  Konuşma geçmişi PostgreSQL chat_messages tablosunda tutulur.
  Her istek geldiğinde main.py, DB'den son MAX_HISTORY mesajı çekip
  ChatInput.history listesine doldurur ve bu servisi çağırır.
  LLM her turda tam bağlamı görür — harici bir vektör DB'ye gerek yok.

Kullanım (main.py içinden):
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

MAX_HISTORY = 20   # LLM'e gönderilecek maksimum geçmiş mesaj sayısı


def _load_coach_prompt() -> str:
    global _CACHED_PROMPT
    if _CACHED_PROMPT is None:
        _CACHED_PROMPT = (
            _PROMPT_PATH.read_text(encoding="utf-8")
            if _PROMPT_PATH.exists()
            else "Sen uzman bir kişisel antrenörsün. Güvenli ve etkili egzersiz tavsiyeleri ver."
        )
    return _CACHED_PROMPT


# ─── Veri Sınıfları ───────────────────────────────────────────────────────────

@dataclass
class HealthConditionCtx:
    condition_type: str       # lumbar_hernia | knee_injury | ...
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
    """
    POST /chat/message'dan gelen ve servise iletilen tüm bağlam.

    session_id: None → yeni oturum açılır; dolu → mevcut oturum devam eder.
    history: [{"role": "user"|"assistant", "content": "..."}]
             main.py bu listeyi DB'den doldurup iletir.
    """
    user_id: str
    user_name: str
    message: str
    session_id: Optional[str] = None
    health_conditions: list[HealthConditionCtx] = field(default_factory=list)
    active_plan: Optional[ActivePlanCtx] = None
    history: list[dict] = field(default_factory=list)
    preferred_provider: str = "auto"


@dataclass
class PlanUpdateAction:
    """LLM'in PLAN_UPDATE bloğundan parse edilen egzersiz değişikliği."""
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
        """chat_messages tablosuna yazılacak kullanıcı mesajı satırı."""
        return {
            "role": "user",
            "content": self._raw_user_message,
            "token_count": None,
            "plan_update_diff": None,
        }

    def assistant_db_row(self) -> dict:
        """chat_messages tablosuna yazılacak asistan yanıtı satırı."""
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


# ─── Sistem Promptu Builder ───────────────────────────────────────────────────

def _build_system_prompt(data: ChatInput) -> str:
    """
    Her turda kullanıcıya özgü sistem promptu üretir.
    Temel persona + kullanıcı adı + aktif sağlık koşulları + aktif plan.
    """
    lines = [_load_coach_prompt(), "",
             "════════════════════════════════════════",
             "MEVCUT KULLANICI PROFİLİ",
             "════════════════════════════════════════",
             f"Ad: {data.user_name}"]

    if data.health_conditions:
        lines.append("\nSağlık Koşulları ⚠️ — tetikleyen egzersizleri ASLA önerme:")
        for c in data.health_conditions:
            region = f" ({c.affected_region})" if c.affected_region else ""
            lines.append(f"  • {c.condition_type}{region} — {c.severity}")
    else:
        lines.append("Sağlık Koşulları: Yok")

    if data.active_plan:
        p = data.active_plan
        lines += [
            "",
            "Aktif Plan:",
            f"  • {p.plan_name} | Haftada {p.sessions_per_week} gün | Hedef: {p.primary_goal} | Hafta {p.current_week}",
        ]
        if p.current_week_exercises:
            lines.append("  • Bu haftanın egzersizleri: " + ", ".join(p.current_week_exercises))

    return "\n".join(lines)


# ─── PLAN_UPDATE Parser ───────────────────────────────────────────────────────

_UPDATE_RE = re.compile(r"PLAN_UPDATE:\s*(\{.+?\})", re.DOTALL)


def _parse_plan_update(raw: str) -> tuple[str, Optional[PlanUpdateAction]]:
    """
    LLM yanıtının sonundaki PLAN_UPDATE bloğunu bulur ve ayırır.
    Dönüş: (temizlenmiş_yanıt, PlanUpdateAction | None)
    """
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
        return clean, None   # JSON bozuksa sessizce atla


# ─── LLM Çağrıları ───────────────────────────────────────────────────────────

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


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

async def chat_with_coach(data: ChatInput) -> ChatOutput:
    """
    Kullanıcı mesajını geçmiş bağlamıyla LLM'e gönderir ve yanıtı döner.

    main.py'de tipik kullanım:
        # 1. DB'den geçmişi çek
        rows = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.sent_at)
            .limit(MAX_HISTORY)
        )
        history = [{"role": r.role, "content": r.content} for r in rows.scalars()]

        # 2. Servisi çağır
        out = await chat_with_coach(ChatInput(..., history=history))

        # 3. İki mesajı DB'ye kaydet
        db.add(ChatMessage(session_id=out.session_id, **out.user_db_row()))
        db.add(ChatMessage(session_id=out.session_id, **out.assistant_db_row()))
        await db.commit()

        # 4. Egzersiz değişikliği varsa uygula
        if out.plan_update:
            await swap_exercise_in_plan(db, out.plan_update)
    """
    provider = data.preferred_provider
    if provider == "auto":
        if _OPENAI_OK and getattr(settings, "openai_api_key", None):
            provider = "openai"
        elif _ANTHROPIC_OK and getattr(settings, "anthropic_api_key", None):
            provider = "anthropic"
        else:
            raise RuntimeError("LLM API anahtarı bulunamadı.")

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
