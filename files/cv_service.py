"""
cv_service.py — Posture and body analysis service

Usage (from main.py):
    from cv_service import analyze_posture, PostureResult

Dependencies (pip install):
    pip install mediapipe opencv-python-headless numpy

Supported photo angles:
    "front"  → shoulder tilt, hip tilt, spine lateral deviation, shoulder width ratio
    "back"   → same metrics (rear view verification)
    "left"   → head forward tilt, torso lean (sagittal plane)
    "right"  → same (right profile verification)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import mediapipe as mp

# ─── Constants ────────────────────────────────────────────────────────────────

class LM(int, Enum):
    NOSE           = 0
    LEFT_EAR       = 7
    RIGHT_EAR      = 8
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


# Posture score thresholds (angle deviation → score drop)
TILT_THRESHOLDS = {
    "excellent": 1.0,   # < 1° → excellent
    "good":      3.0,   # 1–3° → good
    "fair":      6.0,  # 3–6° → fair
}


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class Point2D:
    x: float  # 0.0–1.0 normalized (relative to image width)
    y: float  # 0.0–1.0 normalized (relative to image height)
    visibility: float = 0.0  # MediaPipe confidence score


@dataclass
class PostureMetrics:
    shoulder_tilt_deg: Optional[float] = None     # Shoulder level angle (0° = perfectly horizontal)
    hip_tilt_deg: Optional[float] = None          # Hip level angle
    spine_lateral_dev_deg: Optional[float] = None # Spine lateral deviation
    shoulder_width_ratio: Optional[float] = None  # Shoulder width / hip width ratio

    head_forward_deg: Optional[float] = None      # Head forward tilt (0° = upright)
    torso_lean_deg: Optional[float] = None        # Torso forward lean

    photo_angle: str = "front"
    detection_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class PostureResult:
    success: bool
    photo_angle: str
    posture_score: float                          # Overall score between 0–100
    metrics: PostureMetrics
    landmarks_raw: dict                           # Raw coordinates to be saved to DB
    annotated_image_bytes: Optional[bytes] = None # Image with landmark annotations overlay
    error_message: Optional[str] = None

    def to_db_dict(self) -> dict:
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


# ─── Helper Math Functions (WITH ASPECT RATIO CORRECTION) ─────────────────────

def _angle_from_horizontal(p1: Point2D, p2: Point2D, w: int = 1, h: int = 1) -> float:
    """
    Returns the angle of the line between two points relative to the horizontal axis (degrees).
    Uses image width (w) and height (h) to prevent portrait/landscape distortion.
    Guarantees a value between 0° and 90°.
    """
    dx = (p2.x - p1.x) * w
    dy = (p2.y - p1.y) * h
    if dx == 0:
        return 90.0

    angle_deg = abs(math.degrees(math.atan2(dy, dx)))
    if angle_deg > 90.0:
        angle_deg = 180.0 - angle_deg

    return abs(angle_deg)


def _angle_from_vertical(p_top: Point2D, p_bottom: Point2D, w: int = 1, h: int = 1) -> float:
    """
    Returns the deviation of the line between two points relative to the vertical axis.
    Uses image width (w) and height (h) to prevent portrait/landscape distortion.
    Guarantees a value between 0° and 90°.
    """
    dx = abs(p_bottom.x - p_top.x) * w
    dy = abs(p_bottom.y - p_top.y) * h
    if dy == 0:
        return 90.0

    angle_deg = math.degrees(math.atan2(dx, dy))
    return abs(angle_deg)


def _midpoint(p1: Point2D, p2: Point2D) -> Point2D:
    return Point2D(x=(p1.x + p2.x) / 2, y=(p1.y + p2.y) / 2)


def _score_from_angle(angle_deg: float) -> float:
    """
    Converts angle deviation into a 0–100 score.
    0° deviation → 100 points, 15°+ deviation → 0 points.
    """
    abs_angle = abs(angle_deg)
    if abs_angle <= TILT_THRESHOLDS["excellent"]:
        return 100.0
    elif abs_angle <= TILT_THRESHOLDS["good"]:
        return 100.0 - ((abs_angle - 1.0) / 2.0) * 25.0
    elif abs_angle <= TILT_THRESHOLDS["fair"]:
        return 75.0 - ((abs_angle - 3.0) / 3.0) * 35.0
    else:
        return max(0.0, 40.0 - (abs_angle - 6.0) * 10.0)


def _min_visibility(points: list[Point2D], threshold: float = 0.5) -> bool:
    return all(p.visibility >= threshold for p in points)


# ─── MediaPipe Pose Wrapper ───────────────────────────────────────────────────

class PoseDetector:
    def __init__(self, min_detection_confidence: float = 0.5, min_tracking_confidence: float = 0.5):
        self._mp_pose = mp.solutions.pose
        self._mp_draw = mp.solutions.drawing_utils

        self._pose = self._mp_pose.Pose(
            static_image_mode=True,
            model_complexity=2,
            enable_segmentation=False,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def detect(self, image_bgr: np.ndarray) -> tuple[bool, dict, np.ndarray]:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        results = self._pose.process(image_rgb)

        if not results.pose_landmarks:
            return False, {}, image_bgr.copy()

        lm_dict: dict[str, Point2D] = {}
        for lm_enum in LM:
            lm = results.pose_landmarks.landmark[lm_enum.value]
            lm_dict[lm_enum.name] = Point2D(
                x=round(lm.x, 4),
                y=round(lm.y, 4),
                visibility=round(lm.visibility, 3),
            )

        annotated = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        self._mp_draw.draw_landmarks(
            annotated,
            results.pose_landmarks,
            self._mp_pose.POSE_CONNECTIONS,
            self._mp_draw.DrawingSpec(color=(139, 92, 246), thickness=2, circle_radius=3),
            self._mp_draw.DrawingSpec(color=(20, 184, 166), thickness=2),
        )

        return True, lm_dict, annotated

    def close(self):
        self._pose.close()


_detector: Optional[PoseDetector] = None


def get_detector() -> PoseDetector:
    global _detector
    if _detector is None:
        _detector = PoseDetector()
    return _detector


# ─── Metric Calculators ───────────────────────────────────────────────────────

def _compute_front_back_metrics(lm: dict[str, Point2D], w: int = 1, h: int = 1) -> PostureMetrics:
    metrics = PostureMetrics(photo_angle="front")
    warnings: list[str] = []

    l_shoulder = lm.get("LEFT_SHOULDER")
    r_shoulder = lm.get("RIGHT_SHOULDER")
    l_hip      = lm.get("LEFT_HIP")
    r_hip      = lm.get("RIGHT_HIP")

    # ── Shoulder level tilt angle ──
    if l_shoulder and r_shoulder and _min_visibility([l_shoulder, r_shoulder]):
        tilt = _angle_from_horizontal(l_shoulder, r_shoulder, w, h)
        metrics.shoulder_tilt_deg = round(tilt, 2)
        if abs(tilt) > TILT_THRESHOLDS["fair"]:
            warnings.append(f"Significant shoulder tilt detected ({tilt:.1f}°). Potential trapezius muscle imbalance.")
        elif abs(tilt) > TILT_THRESHOLDS["good"]:
            warnings.append(f"Slight shoulder tilt ({tilt:.1f}°).")

    # ── Hip level tilt angle ──
    if l_hip and r_hip and _min_visibility([l_hip, r_hip]):
        hip_tilt = _angle_from_horizontal(l_hip, r_hip, w, h)
        metrics.hip_tilt_deg = round(hip_tilt, 2)
        if abs(hip_tilt) > TILT_THRESHOLDS["fair"]:
            warnings.append(f"Significant hip tilt detected ({hip_tilt:.1f}°). Pelvic imbalance should be evaluated.")

    # ── Spine lateral deviation ──
    if all(p is not None for p in [l_shoulder, r_shoulder, l_hip, r_hip]):
        shoulder_mid = _midpoint(l_shoulder, r_shoulder)
        hip_mid      = _midpoint(l_hip, r_hip)
        lateral_dev  = _angle_from_vertical(shoulder_mid, hip_mid, w, h)
        metrics.spine_lateral_dev_deg = round(lateral_dev, 2)
        if lateral_dev > TILT_THRESHOLDS["fair"]:
            warnings.append(f"High spine lateral deviation ({lateral_dev:.1f}°). Evaluation recommended for scoliosis risk.")

    # ── Shoulder width / hip width ratio ──
    if all(p is not None for p in [l_shoulder, r_shoulder, l_hip, r_hip]):
        shoulder_w = abs(r_shoulder.x - l_shoulder.x)
        hip_w      = abs(r_hip.x - l_hip.x)
        if hip_w > 0:
            metrics.shoulder_width_ratio = round(shoulder_w / hip_w, 3)

    metrics.warnings = warnings
    return metrics


def _compute_side_metrics(lm: dict[str, Point2D], w: int = 1, h: int = 1) -> PostureMetrics:
    metrics = PostureMetrics(photo_angle="left")
    warnings: list[str] = []

    l_ear      = lm.get("LEFT_EAR")
    r_ear      = lm.get("RIGHT_EAR")
    nose       = lm.get("NOSE")
    l_shoulder = lm.get("LEFT_SHOULDER")
    r_shoulder = lm.get("RIGHT_SHOULDER")
    l_hip      = lm.get("LEFT_HIP")
    r_hip      = lm.get("RIGHT_HIP")

    ear      = l_ear      if (l_ear      and l_ear.visibility      > (r_ear.visibility      if r_ear      else 0)) else r_ear
    shoulder = l_shoulder if (l_shoulder and l_shoulder.visibility > (r_shoulder.visibility if r_shoulder else 0)) else r_shoulder
    hip      = l_hip      if (l_hip      and l_hip.visibility      > (r_hip.visibility      if r_hip      else 0)) else r_hip

    # ── Head forward tilt (Ear to Shoulder, with Nose fallback) ──
    head_ref = ear if (ear and ear.visibility >= 0.3) else nose
    if head_ref and shoulder and _min_visibility([head_ref, shoulder], threshold=0.3):
        dx = abs(head_ref.x - shoulder.x) * w
        dy = abs(shoulder.y - head_ref.y) * h
        head_forward = math.degrees(math.atan2(dx, dy)) if dy > 0 else 0.0
        metrics.head_forward_deg = round(head_forward, 2)
        if head_forward > 15:
            warnings.append(f"Significant head forward tilt ({head_forward:.1f}°). Strain on neck muscles.")
        elif head_forward > 8:
            warnings.append(f"Slight head forward tilt ({head_forward:.1f}°).")

    # ── Torso lean ──
    if shoulder and hip and _min_visibility([shoulder, hip], threshold=0.4):
        torso_lean = _angle_from_vertical(shoulder, hip, w, h)
        metrics.torso_lean_deg = round(torso_lean, 2)
        if torso_lean > 12:
            warnings.append(f"High torso forward lean ({torso_lean:.1f}°). Possible core muscle weakness.")

    metrics.warnings = warnings
    return metrics


# ─── Score Calculation ────────────────────────────────────────────────────────

def _calculate_posture_score(metrics: PostureMetrics) -> float:
    scores: list[tuple[float, float]] = []

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

    total_weight = sum(w for _, w in scores)
    weighted_sum = sum(s * w for s, w in scores)
    return round(weighted_sum / total_weight, 1)


# ─── Main Function ────────────────────────────────────────────────────────────

def analyze_posture(
    image_source: bytes | str | Path,
    photo_angle: str = "front",
    return_annotated: bool = True,
) -> PostureResult:
    try:
        if isinstance(image_source, (str, Path)):
            image_bgr = cv2.imread(str(image_source))
            if image_bgr is None:
                raise ValueError(f"File could not be read: {image_source}")
        elif isinstance(image_source, bytes):
            nparr = np.frombuffer(image_source, np.uint8)
            image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image_bgr is None:
                raise ValueError("Bytes data could not be converted to a valid image.")
        else:
            raise TypeError(f"Unsupported image_source type: {type(image_source)}")
    except Exception as exc:
        return PostureResult(
            success=False,
            photo_angle=photo_angle,
            posture_score=0.0,
            metrics=PostureMetrics(photo_angle=photo_angle),
            landmarks_raw={},
            error_message=f"Image loading error: {exc}",
        )

    h, w = image_bgr.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        image_bgr = cv2.resize(image_bgr, (int(w * scale), int(h * scale)))
        h, w = image_bgr.shape[:2]

    detector = get_detector()
    detected, lm_dict, annotated = detector.detect(image_bgr)

    if not detected:
        return PostureResult(
            success=False,
            photo_angle=photo_angle,
            posture_score=0.0,
            metrics=PostureMetrics(
                photo_angle=photo_angle,
                warnings=["Human pose could not be detected in the photo."]
            ),
            landmarks_raw={},
            error_message="Pose detection failed.",
        )

    detection_confidence = round(
        sum(p.visibility for p in lm_dict.values()) / len(lm_dict), 3
    )

    if photo_angle in ("front", "back"):
        metrics = _compute_front_back_metrics(lm_dict, w, h)
        metrics.photo_angle = photo_angle
    else:
        metrics = _compute_side_metrics(lm_dict, w, h)
        metrics.photo_angle = photo_angle

    metrics.detection_confidence = detection_confidence
    score = _calculate_posture_score(metrics)

    annotated_bytes: Optional[bytes] = None
    if return_annotated:
        success_enc, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if success_enc:
            annotated_bytes = buffer.tobytes()

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
    supported = {"front", "back", "left", "right"}
    results: dict[str, PostureResult] = {}

    for angle, source in photos.items():
        if angle not in supported:
            continue
        results[angle] = analyze_posture(source, photo_angle=angle, return_annotated=return_annotated)

    return results


def combined_posture_score(results: dict[str, PostureResult]) -> float:
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