"""
cv_service.py — Postür ve vücut analizi servisi

Kullanım (main.py içinden):
    from cv_service import analyze_posture, PostureResult

Bağımlılıklar (pip install):
    pip install mediapipe opencv-python-headless numpy

Desteklenen fotoğraf açıları:
    "front"  → omuz tilt, kalça tilt, omurga lateral sapma, omuz genişliği
    "back"   → aynı metrikler (arka görünüm doğrulama)
    "left"   → baş öne eğimi, torso öne eğimi (sagittal düzlem)
    "right"  → aynı (sağ profil doğrulama)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np


# ─── Sabitler ─────────────────────────────────────────────────────────────────

# Kullandığımız MediaPipe landmark indeksleri
class LM(int, Enum):
    NOSE           = 0
    LEFT_SHOULDER  = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW     = 13
    RIGHT_ELBOW    = 14
    LEFT_HIP       = 23
    RIGHT_HIP      = 24
    LEFT_KNEE      = 25
    RIGHT_KNEE     = 26
    LEFT_ANKLE     = 27
    RIGHT_ANKLE    = 28


# Postür skoru eşikleri (açı farkı → puan düşüşü)
TILT_THRESHOLDS = {
    "excellent": 2.0,   # < 2° → mükemmel
    "good":      5.0,   # 2–5° → iyi
    "fair":      10.0,  # 5–10° → orta
    # 10°+ → kötü
}


# ─── Veri Sınıfları ───────────────────────────────────────────────────────────

@dataclass
class Point2D:
    x: float  # 0.0–1.0 normalize edilmiş (görüntü genişliğine göre)
    y: float  # 0.0–1.0 normalize edilmiş (görüntü yüksekliğine göre)
    visibility: float = 0.0  # MediaPipe güven skoru


@dataclass
class PostureMetrics:
    """Tek bir fotoğraftan hesaplanan tüm metrikler."""

    # ── Ön/Arka açı metrikleri ──
    shoulder_tilt_deg: Optional[float] = None     # Omuz hizası açısı (0° = mükemmel yatay)
    hip_tilt_deg: Optional[float] = None          # Kalça hizası açısı
    spine_lateral_dev_deg: Optional[float] = None # Omurga lateral sapması
    shoulder_width_ratio: Optional[float] = None  # Omuz genişliği / kalça genişliği

    # ── Yan profil metrikleri ──
    head_forward_deg: Optional[float] = None      # Baş öne eğimi (0° = dik)
    torso_lean_deg: Optional[float] = None        # Gövde öne eğimi

    # ── Genel ──
    photo_angle: str = "front"
    detection_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class PostureResult:
    """analyze_posture() fonksiyonunun dönüş değeri."""
    success: bool
    photo_angle: str
    posture_score: float                          # 0–100 arası genel puan
    metrics: PostureMetrics
    landmarks_raw: dict                           # DB'ye kaydedilecek ham koordinatlar
    annotated_image_bytes: Optional[bytes] = None # Üzerine çizim yapılmış görsel
    error_message: Optional[str] = None

    def to_db_dict(self) -> dict:
        """photo_analyses tablosuna kaydedilecek JSONB-uyumlu sözlük."""
        return {
            "posture_score": self.posture_score,
            "posture_landmarks": self.landmarks_raw,
            "body_measurements": {
                "shoulder_tilt_deg": self.metrics.shoulder_tilt_deg,
                "hip_tilt_deg": self.metrics.hip_tilt_deg,
                "spine_lateral_dev_deg": self.metrics.spine_lateral_dev_deg,
                "shoulder_width_ratio": self.metrics.shoulder_width_ratio,
                "head_forward_deg": self.metrics.head_forward_deg,
                "torso_lean_deg": self.metrics.torso_lean_deg,
            },
            "warnings": self.metrics.warnings,
            "detection_confidence": self.metrics.detection_confidence,
        }


# ─── Yardımcı Matematik Fonksiyonları ─────────────────────────────────────────

def _angle_from_horizontal(p1: Point2D, p2: Point2D) -> float:
    """
    İki nokta arasındaki doğrunun yatay eksene göre açısını döner (derece).
    Sonuç: 0° = mükemmel yatay, pozitif = sağ taraf yukarıda.
    """
    dx = p2.x - p1.x
    dy = p2.y - p1.y  # Görüntü koordinatı: y aşağı artar
    angle_rad = math.atan2(dy, dx)
    return math.degrees(angle_rad)


def _angle_from_vertical(p_top: Point2D, p_bottom: Point2D) -> float:
    """
    İki nokta arasındaki doğrunun dikey eksene göre sapmasını döner.
    Sonuç: 0° = mükemmel dikey, pozitif = sağa yatık.
    """
    dx = p_bottom.x - p_top.x
    dy = p_bottom.y - p_top.y
    if dy == 0:
        return 90.0
    angle_rad = math.atan2(abs(dx), abs(dy))
    return math.degrees(angle_rad)


def _midpoint(p1: Point2D, p2: Point2D) -> Point2D:
    return Point2D(x=(p1.x + p2.x) / 2, y=(p1.y + p2.y) / 2)


def _score_from_angle(angle_deg: float) -> float:
    """
    Açı sapmasını 0–100 puana dönüştürür.
    0° sapma → 100 puan, 15°+ sapma → 0 puan (doğrusal düşüş).
    """
    abs_angle = abs(angle_deg)
    if abs_angle <= TILT_THRESHOLDS["excellent"]:
        return 100.0
    elif abs_angle <= TILT_THRESHOLDS["good"]:
        return 100 - ((abs_angle - 2) / 3) * 20   # 100 → 80
    elif abs_angle <= TILT_THRESHOLDS["fair"]:
        return 80 - ((abs_angle - 5) / 5) * 40    # 80 → 40
    else:
        return max(0.0, 40 - (abs_angle - 10) * 4)


def _min_visibility(points: list[Point2D], threshold: float = 0.5) -> bool:
    """Tüm noktaların görünürlük eşiğini geçip geçmediğini kontrol eder."""
    return all(p.visibility >= threshold for p in points)


# ─── MediaPipe Pose Wrapper ───────────────────────────────────────────────────

class PoseDetector:
    """
    MediaPipe Pose modelini yöneten sınıf.
    Tek seferlik yüklenip tekrar kullanılır (servis başlangıcında init edilir).
    """

    def __init__(self, min_detection_confidence: float = 0.5, min_tracking_confidence: float = 0.5):
        self._mp_pose = mp.solutions.pose
        self._mp_draw = mp.solutions.drawing_utils
        self._pose = self._mp_pose.Pose(
            static_image_mode=True,          # Fotoğraf analizi → tracking kapalı
            model_complexity=2,              # 0/1/2 — 2 en hassas, daha yavaş
            enable_segmentation=False,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def detect(self, image_bgr: np.ndarray) -> tuple[bool, dict, np.ndarray]:
        """
        BGR görüntüden landmark tespiti yapar.

        Returns:
            (başarılı_mı, landmark_sözlüğü, annotated_image)
        """
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image_rgb.flags.writeable = False
        results = self._mp_pose.Pose.process(self._pose, image_rgb)
        image_rgb.flags.writeable = True

        # MediaPipe'ın kendi process metodunu kullanıyoruz
        results = self._pose.process(image_rgb)

        if not results.pose_landmarks:
            return False, {}, image_bgr.copy()

        # Landmark'ları sözlüğe dönüştür
        lm_dict: dict[str, Point2D] = {}
        for lm_enum in LM:
            lm = results.pose_landmarks.landmark[lm_enum.value]
            lm_dict[lm_enum.name] = Point2D(
                x=round(lm.x, 4),
                y=round(lm.y, 4),
                visibility=round(lm.visibility, 3),
            )

        # Üzerine çizim yapılmış görsel
        annotated = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        self._mp_draw.draw_landmarks(
            annotated,
            results.pose_landmarks,
            self._mp_pose.POSE_CONNECTIONS,
            self._mp_draw.DrawingSpec(color=(139, 92, 246), thickness=2, circle_radius=3),  # mor nokta
            self._mp_draw.DrawingSpec(color=(20, 184, 166), thickness=2),                   # teal çizgi
        )

        return True, lm_dict, annotated

    def close(self):
        self._pose.close()


# Modül düzeyinde tek örnek (FastAPI app başlangıcında oluşturulur)
_detector: Optional[PoseDetector] = None


def get_detector() -> PoseDetector:
    global _detector
    if _detector is None:
        _detector = PoseDetector()
    return _detector


# ─── Metrik Hesaplayıcılar ────────────────────────────────────────────────────

def _compute_front_back_metrics(lm: dict[str, Point2D]) -> PostureMetrics:
    """
    Ön veya arka fotoğraf için metrikleri hesaplar.
    Kullanılan landmark'lar: #11, #12 (omuz), #23, #24 (kalça), #0 (burun)
    """
    metrics = PostureMetrics(photo_angle="front")
    warnings: list[str] = []

    l_shoulder = lm.get("LEFT_SHOULDER")
    r_shoulder = lm.get("RIGHT_SHOULDER")
    l_hip      = lm.get("LEFT_HIP")
    r_hip      = lm.get("RIGHT_HIP")
    nose       = lm.get("NOSE")

    # ── Omuz hizası tilt açısı ──
    if l_shoulder and r_shoulder and _min_visibility([l_shoulder, r_shoulder]):
        tilt = _angle_from_horizontal(l_shoulder, r_shoulder)
        metrics.shoulder_tilt_deg = round(tilt, 2)
        if abs(tilt) > TILT_THRESHOLDS["fair"]:
            warnings.append(
                f"Omuz hizasında belirgin eğim tespit edildi ({tilt:+.1f}°). "
                "Trapez kas dengesizliği olabilir."
            )
        elif abs(tilt) > TILT_THRESHOLDS["good"]:
            warnings.append(f"Hafif omuz eğimi ({tilt:+.1f}°).")

    # ── Kalça hizası tilt açısı ──
    if l_hip and r_hip and _min_visibility([l_hip, r_hip]):
        hip_tilt = _angle_from_horizontal(l_hip, r_hip)
        metrics.hip_tilt_deg = round(hip_tilt, 2)
        if abs(hip_tilt) > TILT_THRESHOLDS["fair"]:
            warnings.append(
                f"Kalça hizasında belirgin eğim ({hip_tilt:+.1f}°). "
                "Pelvik dengesizlik veya bacak boyu farkı değerlendirilmeli."
            )

    # ── Omurga lateral sapması ──
    if all(p is not None for p in [l_shoulder, r_shoulder, l_hip, r_hip]):
        shoulder_mid = _midpoint(l_shoulder, r_shoulder)
        hip_mid      = _midpoint(l_hip, r_hip)
        lateral_dev  = _angle_from_vertical(shoulder_mid, hip_mid)
        metrics.spine_lateral_dev_deg = round(lateral_dev, 2)
        if lateral_dev > TILT_THRESHOLDS["fair"]:
            warnings.append(
                f"Omurga lateral sapması yüksek ({lateral_dev:.1f}°). "
                "Skolyoz riski için profesyonel değerlendirme önerilir."
            )

    # ── Omuz genişliği / kalça genişliği oranı ──
    if all(p is not None for p in [l_shoulder, r_shoulder, l_hip, r_hip]):
        shoulder_w = abs(r_shoulder.x - l_shoulder.x)
        hip_w      = abs(r_hip.x - l_hip.x)
        if hip_w > 0:
            metrics.shoulder_width_ratio = round(shoulder_w / hip_w, 3)

    metrics.warnings = warnings
    return metrics


def _compute_side_metrics(lm: dict[str, Point2D]) -> PostureMetrics:
    """
    Sol veya sağ profil fotoğrafı için metrikleri hesaplar.
    Sagittal düzlem: baş öne eğimi ve gövde eğimi.
    """
    metrics = PostureMetrics(photo_angle="left")
    warnings: list[str] = []

    nose      = lm.get("NOSE")
    l_shoulder = lm.get("LEFT_SHOULDER")
    r_shoulder = lm.get("RIGHT_SHOULDER")
    l_hip      = lm.get("LEFT_HIP")
    r_hip      = lm.get("RIGHT_HIP")

    # Profilden daha iyi görünen omuz/kalça tarafını seç
    shoulder = l_shoulder if (l_shoulder and l_shoulder.visibility > (r_shoulder.visibility if r_shoulder else 0)) else r_shoulder
    hip      = l_hip      if (l_hip      and l_hip.visibility      > (r_hip.visibility      if r_hip      else 0)) else r_hip

    # ── Baş öne eğimi (Forward Head Posture) ──
    if nose and shoulder and _min_visibility([nose, shoulder], threshold=0.4):
        # Burun x konumu ile omuz x konumu farkı → öne uzanma
        dx = nose.x - shoulder.x           # normalize koordinat
        dy = shoulder.y - nose.y           # omuz kulak seviyesinden aşağıda olduğu için pozitif
        head_forward = math.degrees(math.atan2(abs(dx), abs(dy))) if dy > 0 else 0.0
        metrics.head_forward_deg = round(head_forward, 2)
        if head_forward > 15:
            warnings.append(
                f"Belirgin baş öne eğimi ({head_forward:.1f}°). "
                "Boyun kaslarında yüklenme ve boyun fıtığı riski var."
            )
        elif head_forward > 8:
            warnings.append(f"Hafif baş öne eğimi ({head_forward:.1f}°).")

    # ── Gövde öne eğimi (Torso Lean) ──
    if shoulder and hip and _min_visibility([shoulder, hip], threshold=0.4):
        torso_lean = _angle_from_vertical(shoulder, hip)
        metrics.torso_lean_deg = round(torso_lean, 2)
        if torso_lean > 12:
            warnings.append(
                f"Gövde öne eğimi yüksek ({torso_lean:.1f}°). "
                "Core kasları zayıflığı veya bel fıtığı postürü olabilir."
            )

    metrics.warnings = warnings
    return metrics


# ─── Puan Hesaplama ───────────────────────────────────────────────────────────

def _calculate_posture_score(metrics: PostureMetrics) -> float:
    """
    Metriklerin ağırlıklı ortalamasından 0–100 arası puan üretir.

    Ağırlıklar:
      - Omuz tilti:         %30
      - Kalça tilti:        %25
      - Omurga lateral:     %25
      - Baş öne eğimi:      %15
      - Gövde eğimi:        %5
    """
    scores: list[tuple[float, float]] = []  # (puan, ağırlık)

    if metrics.shoulder_tilt_deg is not None:
        scores.append((_score_from_angle(metrics.shoulder_tilt_deg), 0.30))
    if metrics.hip_tilt_deg is not None:
        scores.append((_score_from_angle(metrics.hip_tilt_deg), 0.25))
    if metrics.spine_lateral_dev_deg is not None:
        scores.append((_score_from_angle(metrics.spine_lateral_dev_deg), 0.25))
    if metrics.head_forward_deg is not None:
        scores.append((_score_from_angle(metrics.head_forward_deg), 0.15))
    if metrics.torso_lean_deg is not None:
        scores.append((_score_from_angle(metrics.torso_lean_deg), 0.05))

    if not scores:
        return 0.0

    # Mevcut metriklerin ağırlıklarını normalize et
    total_weight = sum(w for _, w in scores)
    weighted_sum = sum(s * w for s, w in scores)
    return round(weighted_sum / total_weight, 1)


# ─── Ana Fonksiyon ────────────────────────────────────────────────────────────

def analyze_posture(
    image_source: bytes | str | Path,
    photo_angle: str = "front",
    return_annotated: bool = True,
) -> PostureResult:
    """
    Tek bir fotoğraftan postür analizi yapar.

    Args:
        image_source: Ham bytes (multipart upload) veya dosya yolu.
        photo_angle:  "front" | "back" | "left" | "right"
        return_annotated: True ise çizimli görseli de döner (önizleme için).

    Returns:
        PostureResult — .to_db_dict() ile doğrudan DB'ye kaydedilebilir.

    Kullanım örneği (main.py içinde):
        result = analyze_posture(await file.read(), photo_angle="front")
        if result.success:
            score = result.posture_score
            db_data = result.to_db_dict()
    """
    # ── Görüntü yükle ──
    try:
        if isinstance(image_source, (str, Path)):
            image_bgr = cv2.imread(str(image_source))
            if image_bgr is None:
                raise ValueError(f"Dosya okunamadı: {image_source}")
        elif isinstance(image_source, bytes):
            nparr = np.frombuffer(image_source, np.uint8)
            image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image_bgr is None:
                raise ValueError("Bytes verisi geçerli bir görüntüye dönüştürülemedi.")
        else:
            raise TypeError(f"Desteklenmeyen image_source tipi: {type(image_source)}")
    except Exception as exc:
        return PostureResult(
            success=False,
            photo_angle=photo_angle,
            posture_score=0.0,
            metrics=PostureMetrics(photo_angle=photo_angle),
            landmarks_raw={},
            error_message=f"Görüntü yükleme hatası: {exc}",
        )

    # ── Görüntüyü ön işle ──
    # Uzun kenarı 1024px ile sınırla (hız/doğruluk dengesi)
    h, w = image_bgr.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        image_bgr = cv2.resize(image_bgr, (int(w * scale), int(h * scale)))

    # ── MediaPipe tespiti ──
    detector = get_detector()
    detected, lm_dict, annotated = detector.detect(image_bgr)

    if not detected:
        return PostureResult(
            success=False,
            photo_angle=photo_angle,
            posture_score=0.0,
            metrics=PostureMetrics(
                photo_angle=photo_angle,
                warnings=["Fotoğrafta insan pozu tespit edilemedi. "
                          "Lütfen tüm vücudun göründüğü, iyi ışıklı bir fotoğraf yükleyin."]
            ),
            landmarks_raw={},
            error_message="Pose tespiti başarısız.",
        )

    # Ortalama görünürlük → tespit güveni
    detection_confidence = round(
        sum(p.visibility for p in lm_dict.values()) / len(lm_dict), 3
    )

    # ── Açıya göre metrik hesapla ──
    if photo_angle in ("front", "back"):
        metrics = _compute_front_back_metrics(lm_dict)
        metrics.photo_angle = photo_angle
    else:  # left, right
        metrics = _compute_side_metrics(lm_dict)
        metrics.photo_angle = photo_angle

    metrics.detection_confidence = detection_confidence

    # ── Puan hesapla ──
    score = _calculate_posture_score(metrics)

    # ── Annotated görsel (opsiyonel) ──
    annotated_bytes: Optional[bytes] = None
    if return_annotated:
        success_enc, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if success_enc:
            annotated_bytes = buffer.tobytes()

    # ── Landmark'ları serileştir ──
    landmarks_raw = {
        name: {"x": p.x, "y": p.y, "visibility": p.visibility}
        for name, p in lm_dict.items()
    }

    return PostureResult(
        success=True,
        photo_angle=photo_angle,
        posture_score=score,
        metrics=metrics,
        landmarks_raw=landmarks_raw,
        annotated_image_bytes=annotated_bytes,
    )


def analyze_multi_angle(
    photos: dict[str, bytes | str | Path],
    return_annotated: bool = False,
) -> dict[str, PostureResult]:
    """
    Birden fazla açıdan fotoğraf analizi yapar ve sonuçları birleştirir.

    Args:
        photos: {"front": <bytes>, "left": <bytes>, ...}

    Returns:
        {"front": PostureResult, "left": PostureResult, ...}

    Kullanım (main.py içinde):
        results = analyze_multi_angle({
            "front": front_bytes,
            "left":  left_bytes,
        })
        avg_score = sum(r.posture_score for r in results.values()) / len(results)
    """
    supported = {"front", "back", "left", "right"}
    results: dict[str, PostureResult] = {}

    for angle, source in photos.items():
        if angle not in supported:
            continue
        results[angle] = analyze_posture(source, photo_angle=angle, return_annotated=return_annotated)

    return results


def combined_posture_score(results: dict[str, PostureResult]) -> float:
    """
    Çoklu açı analizinden tek bir genel postür skoru üretir.

    Ağırlıklar:
      front → %40, back → %25, left → %20, right → %15
    """
    weights = {"front": 0.40, "back": 0.25, "left": 0.20, "right": 0.15}
    total_score = 0.0
    total_weight = 0.0

    for angle, result in results.items():
        if result.success and angle in weights:
            total_score  += result.posture_score * weights[angle]
            total_weight += weights[angle]

    if total_weight == 0:
        return 0.0
    return round(total_score / total_weight, 1)
