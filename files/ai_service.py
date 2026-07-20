"""
ai_service.py — LLM tabanlı antrenman programı üretici

Kullanım (main.py içinden):
    from ai_service import generate_workout_plan, WorkoutPlanInput

Desteklenen LLM sağlayıcılar:
    - OpenAI  (OPENAI_API_KEY)
    - Anthropic / Claude  (ANTHROPIC_API_KEY)
    Hangisi .env'de tanımlıysa o kullanılır; ikisi de varsa OpenAI öncelikli.

Bağımlılıklar:
    pip install openai anthropic
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ─── Lazy import — yalnızca kullanılan SDK yüklenir ──────────────────────────
try:
    from openai import AsyncOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

try:
    from anthropic import AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
from __future__ import annotations
import os
from dotenv import load_dotenv
load_dotenv(override=True)
from config import get_settings

settings = get_settings()

# System prompt dosyası (düz klasör yapısı → prompts/workout_system.txt)
_PROMPT_PATH = Path(__file__).parent / "prompts" / "workout_system.txt"
_SYSTEM_PROMPT: Optional[str] = None


def _load_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        if _PROMPT_PATH.exists():
            _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
        else:
            # Fallback: prompt dosyası bulunamazsa minimum prompt
            _SYSTEM_PROMPT = (
                "Sen uzman bir kişisel antrenörsün. "
                "Kullanıcı profiline göre antrenman programı oluştur. "
                "Yanıtın YALNIZCA JSON olsun, başka hiçbir metin ekleme."
            )
    return _SYSTEM_PROMPT


# ─── Veri Sınıfları ───────────────────────────────────────────────────────────

@dataclass
class HealthConditionInput:
    condition_type: str   # lumbar_hernia | knee_injury | shoulder_injury | ...
    severity: str         # mild | moderate | severe
    affected_region: Optional[str] = None
    description: Optional[str] = None


@dataclass
class PostureMetricsInput:
    """cv_service.py'den gelen postür metrikleri (opsiyonel)."""
    shoulder_tilt_deg: Optional[float] = None
    hip_tilt_deg: Optional[float] = None
    spine_lateral_dev_deg: Optional[float] = None
    shoulder_width_ratio: Optional[float] = None
    head_forward_deg: Optional[float] = None
    torso_lean_deg: Optional[float] = None
    posture_score: Optional[float] = None


@dataclass
class WorkoutPlanInput:
    """
    LLM'e gönderilecek tüm kullanıcı bağlamı.
    main.py'de DB'den veya request'ten doldurulur.
    """
    # Temel bilgiler
    user_id: str
    full_name: str
    age: int
    gender: str
    height_cm: float
    current_weight_kg: float
    target_weight_kg: float
    fitness_level: str          # beginner | intermediate | advanced
    primary_goal: str           # weight_loss | muscle_gain | endurance | flexibility | rehabilitation

    # Sakatlık bilgileri (boş liste = yok)
    health_conditions: list[HealthConditionInput] = field(default_factory=list)

    # Postür metrikleri (cv_service çıktısı, opsiyonel)
    posture_metrics: Optional[PostureMetricsInput] = None

    # Program tercihleri
    available_days_per_week: int = 3          # Kullanıcının antrenman yapabileceği gün sayısı
    available_equipment: list[str] = field(   # Kullanıcının erişebildiği ekipmanlar
        default_factory=lambda: ["dumbbell", "body weight"]
    )
    program_duration_weeks: int = 8           # Kaç haftalık program isteniyor


@dataclass
class GeneratedWorkoutPlan:
    """LLM'den gelen parse edilmiş program + DB'ye yazılmaya hazır payload."""
    raw_json: dict                  # LLM'in ürettiği ham JSON
    db_plan_payload: dict           # workout_plans tablosuna yazılacak alanlar
    db_days_payload: list[dict]     # workout_days satırları
    db_exercises_payload: list[dict]# workout_day_exercises satırları (exercise adıyla birlikte)
    llm_provider: str               # Hangi LLM kullandı
    generation_time_ms: int         # Kaç ms sürdü
    warnings: list[str] = field(default_factory=list)


# ─── Kullanıcı Prompt Builder ─────────────────────────────────────────────────

def _build_user_prompt(data: WorkoutPlanInput) -> str:
    """
    Kullanıcı profilini LLM'in okuyacağı yapılandırılmış metne dönüştürür.
    System prompt'taki JSON şemasını dolduracak bağlamı sağlar.
    """
    bmi = round(data.current_weight_kg / (data.height_cm / 100) ** 2, 1)
    weight_diff = round(data.current_weight_kg - data.target_weight_kg, 1)
    weight_direction = "vermesi" if weight_diff > 0 else "alması"

    lines = [
        "## Kullanıcı Profili",
        f"- Ad: {data.full_name}",
        f"- Yaş: {data.age} | Cinsiyet: {data.gender}",
        f"- Boy: {data.height_cm} cm | Mevcut kilo: {data.current_weight_kg} kg",
        f"- Hedef kilo: {data.target_weight_kg} kg "
        f"(hedef: {abs(weight_diff):.1f} kg {weight_direction})",
        f"- BMI: {bmi}",
        f"- Fitness seviyesi: {data.fitness_level}",
        f"- Birincil hedef: {data.primary_goal}",
        "",
        "## Antrenman Kısıtları",
        f"- Haftada kullanılabilir gün: {data.available_days_per_week}",
        f"- Mevcut ekipman: {', '.join(data.available_equipment)}",
        f"- İstenen program süresi: {data.program_duration_weeks} hafta",
        "",
    ]

    # Sakatlık bilgileri
    if data.health_conditions:
        lines.append("## Sağlık / Sakatlık Durumları  ⚠️ KRİTİK")
        for cond in data.health_conditions:
            desc = f" — {cond.description}" if cond.description else ""
            region = f" ({cond.affected_region})" if cond.affected_region else ""
            lines.append(
                f"- {cond.condition_type}{region}: şiddet={cond.severity}{desc}"
            )
        lines.append(
            "  Bu sakatlıkları tetikleyen EGZERSİZLERİ KESINLIKLE EKLEME. "
            "Her ilgili egzersizin ai_notes alanında sakatlık uyarısı belirt."
        )
        lines.append("")
    else:
        lines.append("## Sağlık Durumu\n- Bilinen sakatlık veya kısıt yok.\n")

    # Postür metrikleri
    if data.posture_metrics:
        pm = data.posture_metrics
        lines.append("## Postür Analizi Sonuçları (CV modülünden)")
        if pm.posture_score is not None:
            lines.append(f"- Genel postür skoru: {pm.posture_score}/100")
        if pm.shoulder_tilt_deg is not None:
            flag = " ⚠️ YÜKSEK" if abs(pm.shoulder_tilt_deg) > 5 else ""
            lines.append(f"- Omuz hizası sapması: {pm.shoulder_tilt_deg:+.1f}°{flag}")
        if pm.hip_tilt_deg is not None:
            flag = " ⚠️ YÜKSEK" if abs(pm.hip_tilt_deg) > 5 else ""
            lines.append(f"- Kalça hizası sapması: {pm.hip_tilt_deg:+.1f}°{flag}")
        if pm.spine_lateral_dev_deg is not None:
            flag = " ⚠️ YÜKSEK" if pm.spine_lateral_dev_deg > 5 else ""
            lines.append(f"- Omurga lateral sapması: {pm.spine_lateral_dev_deg:.1f}°{flag}")
        if pm.head_forward_deg is not None:
            flag = " ⚠️ YÜKSEK" if pm.head_forward_deg > 10 else ""
            lines.append(f"- Baş öne eğimi: {pm.head_forward_deg:.1f}°{flag}")
        if pm.shoulder_width_ratio is not None:
            lines.append(f"- Omuz/kalça genişlik oranı: {pm.shoulder_width_ratio:.2f}")
        lines.append(
            "  Postür sapmaları yüksek olan kaslar için düzeltici egzersizler ekle "
            "ve ai_notes'ta neden eklendiğini belirt."
        )
        lines.append("")

    lines.append(
        "## Görev\n"
        f"Yukarıdaki profile göre {data.program_duration_weeks} haftalık, "
        f"haftada {data.available_days_per_week} gün antrenman içeren, "
        "system prompt'taki JSON şemasına TAMAMEN uyan bir program oluştur.\n"
        "Yanıt: yalnızca JSON. Açıklama, yorum veya markdown yok."
    )

    return "\n".join(lines)


# ─── JSON Temizleyici ─────────────────────────────────────────────────────────

def _extract_json(raw_text: str) -> str:
    """
    LLM bazen JSON'u ```json ... ``` bloğu içine alır veya
    başına/sonuna açıklama ekler. Bu fonksiyon saf JSON'u ayıklar.
    """
    # Markdown kod bloğu varsa içeriği çıkar
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if match:
        return match.group(1)

    # İlk { ile son } arasını al
    start = raw_text.find("{")
    end   = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw_text[start:end + 1]

    return raw_text.strip()


# ─── JSON Doğrulayıcı ─────────────────────────────────────────────────────────

def _validate_plan_json(plan: dict) -> list[str]:
    """
    LLM çıktısını doğrular. Uyarı listesi döner (boşsa hata yok).
    workout_plans, workout_days ve workout_day_exercises tablolarıyla uyumlu mu kontrol eder.
    """
    warnings: list[str] = []
    required_top = ["plan_name", "duration_weeks", "sessions_per_week", "weeks"]
    for key in required_top:
        if key not in plan:
            warnings.append(f"Eksik alan: '{key}'")

    if "weeks" not in plan:
        return warnings

    if not isinstance(plan["weeks"], list) or len(plan["weeks"]) == 0:
        warnings.append("'weeks' boş veya liste değil.")
        return warnings

    for wi, week in enumerate(plan["weeks"]):
        if "days" not in week:
            warnings.append(f"week[{wi}] 'days' içermiyor.")
            continue
        for di, day in enumerate(week["days"]):
            if day.get("day_type") == "workout" and not day.get("exercises"):
                warnings.append(
                    f"week[{wi}].day[{di}] workout tipi ama egzersiz listesi boş."
                )
            for ei, ex in enumerate(day.get("exercises", [])):
                if not ex.get("name"):
                    warnings.append(f"week[{wi}].day[{di}].exercises[{ei}] 'name' yok.")
                if not ex.get("sets"):
                    warnings.append(f"'{ex.get('name','?')}' için 'sets' yok.")
                # order_index kontrolü
                expected_order = ei + 1
                if ex.get("order_index") != expected_order:
                    ex["order_index"] = expected_order  # Otomatik düzelt

    return warnings


# ─── DB Payload Builder ───────────────────────────────────────────────────────

def _build_db_payloads(
    plan: dict, user_id: str
) -> tuple[dict, list[dict], list[dict]]:
    """
    Parse edilmiş JSON'dan 3 ayrı DB payload'u üretir:
      1. workout_plans tablosu için tek satır
      2. workout_days tablosu için satır listesi
      3. workout_day_exercises için satır listesi (exercise name ile; ID eşlemesi servis katmanında yapılır)
    """
    plan_payload = {
        "user_id":          user_id,
        "plan_name":        plan.get("plan_name", "AI Antrenman Programı"),
        "duration_weeks":   plan.get("duration_weeks", 8),
        "sessions_per_week":plan.get("sessions_per_week", 3),
        "difficulty":       plan.get("difficulty", "beginner"),
        "estimated_months": plan.get("estimated_months"),
        "ai_reasoning":     plan.get("ai_reasoning"),
        "is_active":        True,
        "generated_by":     "ai",
    }

    days_payload:      list[dict] = []
    exercises_payload: list[dict] = []

    for week in plan.get("weeks", []):
        week_num = week.get("week_number", 1)
        for day in week.get("days", []):
            day_row = {
                "week_number":  week_num,
                "day_number":   day.get("day_number", 1),
                "day_label":    day.get("day_label"),
                "muscle_focus": day.get("muscle_focus"),
                "day_type":     day.get("day_type", "workout"),
                "_exercises":   [],   # Geçici alan, DB'ye yazılmaz
            }
            for ex in day.get("exercises", []):
                day_row["_exercises"].append({
                    "exercise_name": ex.get("name"),    # exercises tablosunda eşleştirilecek
                    "body_part":     ex.get("body_part"),
                    "equipment":     ex.get("equipment"),
                    "sets":          ex.get("sets", 3),
                    "reps":          str(ex.get("reps", "12")),
                    "rest_seconds":  ex.get("rest_seconds", 60),
                    "order_index":   ex.get("order_index", 1),
                    "ai_notes":      ex.get("ai_notes"),
                })
            days_payload.append(day_row)

    return plan_payload, days_payload, exercises_payload


# ─── LLM Çağrı Fonksiyonları ─────────────────────────────────────────────────

async def _call_openai(system_prompt: str, user_prompt: str) -> str:
    if not _OPENAI_AVAILABLE:
        raise RuntimeError("openai paketi yüklü değil: pip install openai")
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY .env dosyasında tanımlı değil.")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",          # Maliyet/kalite dengesi için mini
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.3,              # Düşük: yaratıcılık değil tutarlılık istiyoruz
        max_tokens=4096,
        response_format={"type": "json_object"},  # OpenAI JSON mode
    )
    return response.choices[0].message.content


async def _call_anthropic(system_prompt: str, user_prompt: str) -> str:
    if not _ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic paketi yüklü değil: pip install anthropic")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY .env dosyasında tanımlı değil.")

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        temperature=0.3,
    )
    return message.content[0].text


# ─── Ana Servis Fonksiyonu ────────────────────────────────────────────────────

async def generate_workout_plan(
    data: WorkoutPlanInput,
    preferred_provider: str = "auto",   # "auto" | "openai" | "anthropic"
) -> GeneratedWorkoutPlan:
    """
    Kullanıcı profilinden LLM aracılığıyla antrenman programı üretir.

    Args:
        data: WorkoutPlanInput — kullanıcı profili + sakatlık + postür metrikleri
        preferred_provider: Hangi LLM kullanılsın. "auto" → .env'de hangisi varsa.

    Returns:
        GeneratedWorkoutPlan — DB'ye yazılmaya hazır payload'larla birlikte.

    Raises:
        ValueError: LLM geçerli JSON döndürmediyse.
        RuntimeError: API anahtarı eksikse veya SDK yüklü değilse.

    Kullanım (main.py içinde):
        result = await generate_workout_plan(plan_input)
        # workout_plans tablosuna yaz:
        plan_id = await db.execute(insert(WorkoutPlan).values(**result.db_plan_payload))
    """
    t_start = time.perf_counter()

    system_prompt = _load_system_prompt()
    user_prompt   = _build_user_prompt(data)

    # Sağlayıcı seçimi
    provider = preferred_provider
    if provider == "auto":
        if _OPENAI_AVAILABLE and getattr(settings, "openai_api_key", None):
            provider = "openai"
        elif _ANTHROPIC_AVAILABLE and getattr(settings, "anthropic_api_key", None):
            provider = "anthropic"
        else:
            raise RuntimeError(
                "Hiçbir LLM API anahtarı bulunamadı. "
                ".env dosyasına OPENAI_API_KEY veya ANTHROPIC_API_KEY ekleyin."
            )

    # LLM çağrısı
    if provider == "openai":
        raw_text = await _call_openai(system_prompt, user_prompt)
    elif provider == "anthropic":
        raw_text = await _call_anthropic(system_prompt, user_prompt)
    else:
        raise ValueError(f"Bilinmeyen sağlayıcı: {provider}. 'openai' veya 'anthropic' kullanın.")

    # JSON ayıklama ve parse
    clean_json = _extract_json(raw_text)
    try:
        plan_dict = json.loads(clean_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM geçerli JSON döndürmedi: {exc}\n"
            f"Ham yanıt (ilk 500 karakter): {raw_text[:500]}"
        ) from exc

    # Doğrulama
    validation_warnings = _validate_plan_json(plan_dict)

    # DB payload'larını oluştur
    plan_payload, days_payload, exercises_payload = _build_db_payloads(
        plan_dict, data.user_id
    )

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    return GeneratedWorkoutPlan(
        raw_json=plan_dict,
        db_plan_payload=plan_payload,
        db_days_payload=days_payload,
        db_exercises_payload=exercises_payload,
        llm_provider=provider,
        generation_time_ms=elapsed_ms,
        warnings=validation_warnings,
    )


# ─── Prompt Önizleme (debug) ─────────────────────────────────────────────────

def preview_prompt(data: WorkoutPlanInput) -> dict[str, str]:
    """
    API çağrısı yapmadan hangi prompt'un gönderileceğini gösterir.
    Geliştirme sırasında endpoint'i test etmek için kullanışlı.

    Kullanım:
        from ai_service import preview_prompt, WorkoutPlanInput
        print(preview_prompt(my_input)["user_prompt"])
    """
    return {
        "system_prompt": _load_system_prompt(),
        "user_prompt":   _build_user_prompt(data),
    }
