"""
progress_service.py — Aylık Postür Gelişim Karşılaştırma Servisi

Ne yapar:
  1. Kullanıcının baseline (1. ay) metriklerini alır.
  2. Yeni fotoğrafı cv_service ile analiz eder.
  3. Metrik farklarını (delta) hesaplar.
  4. LLM'e gönderip Türkçe gelişim raporu üretir.
  5. comparison_delta JSONB alanına kaydedilmek üzere hazır payload döner.

Kullanım (main.py içinden):
    from progress_service import compare_posture, CompareInput, CompareOutput
"""

from __future__ import annotations

import json
import re
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
                "Kullanıcının iki aylık postür metriklerini karşılaştır. "
                "Yalnızca JSON olarak yanıt ver."
            )
        )
    return _CACHED_PROMPT


# ─── Veri Sınıfları ───────────────────────────────────────────────────────────

@dataclass
class BaselineMetrics:
    """
    1. aya ait (veya önceki ölçüme ait) postür metrikleri.
    photo_analyses tablosunun body_measurements JSONB sütunundan doldurulur.
    """
    posture_score: float
    month_number: int                            # Hangi aya ait (1 = başlangıç)
    photo_angle: str = "front"
    shoulder_tilt_deg: Optional[float] = None
    hip_tilt_deg: Optional[float] = None
    spine_lateral_dev_deg: Optional[float] = None
    head_forward_deg: Optional[float] = None
    torso_lean_deg: Optional[float] = None
    shoulder_width_ratio: Optional[float] = None


@dataclass
class CompareInput:
    """POST /analysis/posture/compare endpoint'inden gelen istek."""
    user_id: str
    user_name: str
    # Yeni yüklenen fotoğraf (bytes)
    new_photo_bytes: bytes
    photo_angle: str              # "front" | "back" | "left" | "right"
    new_month_number: int         # Kaçıncı ay (2, 3, 4...)
    # Baseline: DB'den çekilen önceki ay metrikleri
    baseline: BaselineMetrics
    preferred_provider: str = "auto"


@dataclass
class MetricDelta:
    """Tek bir metrik için önceki-sonraki farkı."""
    metric_name: str
    baseline_value: Optional[float]
    new_value: Optional[float]
    delta: Optional[float]          # new - baseline (negatif = iyileşme, çoğu metrik için)
    change_pct: Optional[float]     # Yüzde değişim
    improved: Optional[bool]        # True = postür açısından iyileşme

    @classmethod
    def compute(
        cls,
        name: str,
        baseline: Optional[float],
        new: Optional[float],
        lower_is_better: bool = True,
    ) -> "MetricDelta":
        """
        lower_is_better=True: açı azaldıysa improved=True (omuz tilt, baş eğimi vb.)
        lower_is_better=False: değer arttıysa improved=True (postür skoru gibi)
        """
        if baseline is None or new is None:
            return cls(name, baseline, new, None, None, None)

        delta = round(new - baseline, 3)
        change_pct = round((delta / baseline) * 100, 1) if baseline != 0 else None
        improved = (delta < 0) if lower_is_better else (delta > 0)
        return cls(name, round(baseline, 3), round(new, 3), delta, change_pct, improved)


@dataclass
class ProgressDelta:
    """Tüm metriklerin karşılaştırma sonuçları."""
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
        """photo_analyses.comparison_delta JSONB sütununa yazılacak sözlük."""
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
    """compare_posture() dönüş değeri."""
    success: bool
    new_posture_score: float
    delta: ProgressDelta
    # LLM'in ürettiği Türkçe rapor (parse edilmiş)
    report: dict
    # DB'ye kaydedilecek ham veri
    new_analysis_db_payload: dict       # photo_analyses satırı
    error_message: Optional[str] = None

    def summary_text(self) -> str:
        """
        Frontend için sade tek paragraf özet.
        LLM raporu yoksa deltaları elle üretir.
        """
        if self.report.get("overall_verdict"):
            return self.report["overall_verdict"]
        d = self.delta
        parts = []
        if d.posture_score.delta is not None:
            sign = "arttı" if d.posture_score.delta > 0 else "düştü"
            parts.append(f"Postür skorunuz {abs(d.posture_score.delta):.1f} puan {sign}.")
        if d.shoulder_tilt.improved is True:
            parts.append(f"Omuz hizası {abs(d.shoulder_tilt.delta):.1f}° düzeldi.")
        return " ".join(parts) or "Analiz tamamlandı."


# ─── Delta Hesaplayıcı ────────────────────────────────────────────────────────

def _compute_delta(baseline: BaselineMetrics, new_result: PostureResult) -> ProgressDelta:
    """İki analiz arasındaki farkları hesaplar."""
    nm = new_result.metrics
    return ProgressDelta(
        posture_score=MetricDelta.compute(
            "posture_score", baseline.posture_score, new_result.posture_score,
            lower_is_better=False,          # Skor arttıysa iyileşme
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


# ─── LLM Rapor Promptu Builder ────────────────────────────────────────────────

def _build_report_user_prompt(
    user_name: str,
    baseline: BaselineMetrics,
    new_result: PostureResult,
    delta: ProgressDelta,
    month_number: int,
) -> str:
    """LLM'e gönderilecek karşılaştırma verisini yapılandırılmış metne dönüştürür."""

    def fmt(val: Optional[float]) -> str:
        return f"{val:.2f}" if val is not None else "ölçülmedi"

    def fmt_delta(m: MetricDelta) -> str:
        if m.delta is None:
            return "karşılaştırılamıyor (eksik veri)"
        sign = "+" if m.delta > 0 else ""
        trend = "✓ iyileşti" if m.improved else ("✗ kötüleşti" if m.improved is False else "—")
        return f"{fmt(m.baseline_value)} → {fmt(m.new_value)} (Δ {sign}{m.delta:.2f}, {m.change_pct:+.1f}%) {trend}"

    nm = new_result.metrics
    lines = [
        f"## Kullanıcı: {user_name}",
        f"## Karşılaştırma: Başlangıç (Ay {baseline.month_number}) → Şimdiki (Ay {month_number})",
        f"## Fotoğraf açısı: {new_result.photo_angle}",
        "",
        "### Postür Skoru (0-100)",
        f"  {fmt_delta(delta.posture_score)}",
        "",
        "### Omuz Hizası Tilt (°, düşük = iyi)",
        f"  {fmt_delta(delta.shoulder_tilt)}",
        "",
        "### Kalça Hizası Tilt (°, düşük = iyi)",
        f"  {fmt_delta(delta.hip_tilt)}",
        "",
        "### Omurga Lateral Sapması (°, düşük = iyi)",
        f"  {fmt_delta(delta.spine_lateral)}",
        "",
        "### Baş Öne Eğimi (°, düşük = iyi)",
        f"  {fmt_delta(delta.head_forward)}",
        "",
        "### Gövde Eğimi (°, düşük = iyi)",
        f"  {fmt_delta(delta.torso_lean)}",
        "",
        f"### Özet: {delta.improved_count()} metrik iyileşti, {delta.worsened_count()} metrik kötüleşti.",
        "",
        "Yeni ölçümdeki uyarılar:",
    ]
    for w in (nm.warnings or []):
        lines.append(f"  - {w}")
    if not nm.warnings:
        lines.append("  (yok)")

    lines.append("\nYukarıdaki verilere dayanarak system prompt'taki JSON formatında gelişim raporu yaz.")
    return "\n".join(lines)


# ─── JSON Ayıklama ────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """LLM metninden JSON bloğunu ayıklar ve parse eder."""
    # Markdown kod bloğu
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # İlk { ... son }
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start: end + 1])
    raise ValueError(f"LLM geçerli JSON döndürmedi. Ham yanıt: {text[:300]}")


# ─── LLM Çağrıları ───────────────────────────────────────────────────────────

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
        model="claude-sonnet-4-6",   # Rapor için daha kaliteli model
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": user}],
        temperature=0.4,
    )
    return resp.content[0].text


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

async def compare_posture(data: CompareInput) -> CompareOutput:
    """
    Yeni fotoğrafı analiz edip baseline ile karşılaştırır ve LLM raporu üretir.

    main.py'de tipik kullanım:
        # 1. Baseline'ı DB'den çek
        row = await db.execute(
            select(PhotoAnalysis)
            .join(ProgressPhoto)
            .where(
                ProgressPhoto.user_id == current_user.id,
                ProgressPhoto.photo_angle == angle,
                ProgressPhoto.month_number == 1,   # Başlangıç ayı
            )
        )
        analysis = row.scalar_one_or_none()
        baseline = BaselineMetrics(
            posture_score=analysis.posture_score,
            month_number=1,
            photo_angle=angle,
            **analysis.body_measurements,   # JSONB sütununu doğrudan aç
        )

        # 2. Servisi çağır
        new_bytes = await new_photo_file.read()
        result = await compare_posture(CompareInput(
            user_id=str(current_user.id),
            user_name=current_user.full_name,
            new_photo_bytes=new_bytes,
            photo_angle=angle,
            new_month_number=2,
            baseline=baseline,
        ))

        # 3. Yeni photo_analyses satırını DB'ye kaydet
        if result.success:
            db.add(PhotoAnalysis(**result.new_analysis_db_payload))
            await db.commit()
    """

    # 1. Yeni fotoğrafı CV servisiyle analiz et
    new_result: PostureResult = analyze_posture(
        data.new_photo_bytes,
        photo_angle=data.photo_angle,
        return_annotated=False,
    )

    if not new_result.success:
        return CompareOutput(
            success=False,
            new_posture_score=0.0,
            delta=_compute_delta(data.baseline, new_result),  # Boş delta
            report={},
            new_analysis_db_payload={},
            error_message=new_result.error_message,
        )

    # 2. Deltaları hesapla
    delta = _compute_delta(data.baseline, new_result)

    # 3. LLM'e rapor ürettir
    provider = data.preferred_provider
    if provider == "auto":
        if _OPENAI_OK and getattr(settings, "openai_api_key", None):
            provider = "openai"
        elif _ANTHROPIC_OK and getattr(settings, "anthropic_api_key", None):
            provider = "anthropic"
        else:
            provider = None

    report: dict = {}
    if provider:
        system = _load_report_prompt()
        user_prompt = _build_report_user_prompt(
            data.user_name, data.baseline, new_result, delta, data.new_month_number
        )
        try:
            raw = (
                await _call_openai_report(system, user_prompt)
                if provider == "openai"
                else await _call_anthropic_report(system, user_prompt)
            )
            report = _extract_json(raw)
        except Exception as e:
            # LLM raporu başarısız olsa da metrik sonuçları döneriz
            report = {"error": f"Rapor üretilemedi: {e}"}

    # 4. DB payload'unu hazırla (photo_analyses tablosu)
    cv_db = new_result.to_db_dict()
    cv_db["comparison_delta"] = delta.to_dict()   # JSONB sütunu

    return CompareOutput(
        success=True,
        new_posture_score=new_result.posture_score,
        delta=delta,
        report=report,
        new_analysis_db_payload={
            **cv_db,
            # Çağıran katman photo_id'yi ekler
        },
    )
