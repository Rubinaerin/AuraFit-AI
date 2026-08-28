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

# MediaPipe landmark indices used in analysis
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


# Posture score thresholds (angle deviation → score drop)
TILT_THRESHOLDS = {
    "excellent": 2.0,   # < 2° → excellent
    "good":      5.0,   # 2–5° → good
    "fair":      10.0,  # 5–10° → fair
    # 10°+ → poor
}


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class Point2D:
    x: float  # 0.0–1.0 normalized (relative to image width)
    y: float  # 0.0–1.0 normalized (relative to image height)
    visibility: float = 0.0  # MediaPipe confidence score


@dataclass
class PostureMetrics:
    """All metrics calculated from a single photograph."""

    # ── Front/Back angle metrics ──
    shoulder_tilt_deg: Optional[float] = None     # Shoulder level angle (0° = perfectly horizontal)
    hip_tilt_deg: Optional[float] = None          # Hip level angle
    spine_lateral_dev_deg: Optional[float] = None # Spine lateral deviation
    shoulder_width_ratio: Optional[float] = None  # Shoulder width / hip width ratio

    # ── Side profile metrics ──
    head_forward_deg: Optional[float] = None      # Head forward tilt (0° = upright)
    torso_lean_deg: Optional[float] = None        # Torso forward lean

    # ── General ──
    photo_angle: str = "front"
    detection_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class PostureResult:
    """Return value of the analyze_posture() function."""
    success: bool
    photo_angle: str
    posture_score: float                          # Overall score between 0–100
    metrics: PostureMetrics
    landmarks_raw: dict                           # Raw coordinates to be saved to DB
    annotated_image_bytes: Optional[bytes] = None # Image with landmark annotations overlay
    error_message: Optional[str] = None

    def to_db_dict(self) -> dict:
        """JSONB-compatible dictionary to be saved to photo_analyses table."""
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


# ─── Helper Math Functions ────────────────────────────────────────────────────

def _angle_from_horizontal(p1: Point2D, p2: Point2D) -> float:
    """
    Returns the angle of the line between two points relative to the horizontal axis (degrees).
    Result: 0° = perfectly horizontal, positive = right side is higher.
    """
    dx = p2.x - p1.x
    dy = p2.y - p1.y  # Image coordinates: y increases downwards
    angle_rad = math.atan2(dy, dx)
    return math.degrees(angle_rad)


def _angle_from_vertical(p_top: Point2D, p_bottom: Point2D) -> float:
    """
    Returns the deviation of the line between two points relative to the vertical axis.
    Result: 0° = perfectly vertical, positive = tilted to the right.
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
    Converts angle deviation into a 0–100 score.
    0° deviation → 100 points, 15°+ deviation → 0 points (linear decrease).
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
    """Checks whether all points exceed the minimum visibility threshold."""
    return all(p.visibility >= threshold for p in points)


# ─── MediaPipe Pose Wrapper ───────────────────────────────────────────────────

class PoseDetector:
    """
    Class managing the MediaPipe Pose model.
    Loaded once and reused (initialized at service startup).
    """

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
        """
        Performs landmark detection on a BGR image.

        Returns:
            (is_successful, landmark_dict, annotated_image)
        """
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image_rgb.flags.writeable = False
        results = self._mp_pose.Pose.process(self._pose, image_rgb)
        image_rgb.flags.writeable = True

        # Using MediaPipe's own process method
        results = self._pose.process(image_rgb)

        if not results.pose_landmarks:
            return False, {}, image_bgr.copy()

        # Convert landmarks into dictionary
        lm_dict: dict[str, Point2D] = {}
        for lm_enum in LM:
            lm = results.pose_landmarks.landmark[lm_enum.value]
            lm_dict[lm_enum.name] = Point2D(
                x=round(lm.x, 4),
                y=round(lm.y, 4),
                visibility=round(lm.visibility, 3),
            )

        # Image with drawn annotations
        annotated = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        self._mp_draw.draw_landmarks(
            annotated,
            results.pose_landmarks,
            self._mp_pose.POSE_CONNECTIONS,
            self._mp_draw.DrawingSpec(color=(139, 92, 246), thickness=2, circle_radius=3),  # purple dot
            self._mp_draw.DrawingSpec(color=(20, 184, 166), thickness=2),                   # teal line
        )

        return True, lm_dict, annotated

    def close(self):
        self._pose.close()


# Module-level single instance (Created on FastAPI app startup)
_detector: Optional[PoseDetector] = None


def get_detector() -> PoseDetector:
    global _detector
    if _detector is None:
        _detector = PoseDetector()
    return _detector


# ─── Metric Calculators ───────────────────────────────────────────────────────

def _compute_front_back_metrics(lm: dict[str, Point2D]) -> PostureMetrics:
    """
    Calculates metrics for front or back photos.
    Used landmarks: #11, #12 (shoulder), #23, #24 (hip), #0 (nose)
    """
    metrics = PostureMetrics(photo_angle="front")
    warnings: list[str] = []

    l_shoulder = lm.get("LEFT_SHOULDER")
    r_shoulder = lm.get("RIGHT_SHOULDER")
    l_hip      = lm.get("LEFT_HIP")
    r_hip      = lm.get("RIGHT_HIP")
    nose       = lm.get("NOSE")

    # ── Shoulder level tilt angle ──
    if l_shoulder and r_shoulder and _min_visibility([l_shoulder, r_shoulder]):
        tilt = _angle_from_horizontal(l_shoulder, r_shoulder)
        metrics.shoulder_tilt_deg = round(tilt, 2)
        if abs(tilt) > TILT_THRESHOLDS["fair"]:
            warnings.append(
                f"Significant shoulder tilt detected ({tilt:+.1f}°). "
                "Potential trapezius muscle imbalance."
            )
        elif abs(tilt) > TILT_THRESHOLDS["good"]:
            warnings.append(f"Slight shoulder tilt ({tilt:+.1f}°).")

    # ── Hip level tilt angle ──
    if l_hip and r_hip and _min_visibility([l_hip, r_hip]):
        hip_tilt = _angle_from_horizontal(l_hip, r_hip)
        metrics.hip_tilt_deg = round(hip_tilt, 2)
        if abs(hip_tilt) > TILT_THRESHOLDS["fair"]:
            warnings.append(
                f"Significant hip tilt detected ({hip_tilt:+.1f}°). "
                "Pelvic imbalance or leg length discrepancy should be evaluated."
            )

    # ── Spine lateral deviation ──
    if all(p is not None for p in [l_shoulder, r_shoulder, l_hip, r_hip]):
        shoulder_mid = _midpoint(l_shoulder, r_shoulder)
        hip_mid      = _midpoint(l_hip, r_hip)
        lateral_dev  = _angle_from_vertical(shoulder_mid, hip_mid)
        metrics.spine_lateral_dev_deg = round(lateral_dev, 2)
        if lateral_dev > TILT_THRESHOLDS["fair"]:
            warnings.append(
                f"High spine lateral deviation ({lateral_dev:.1f}°). "
                "Professional evaluation recommended for scoliosis risk."
            )

    # ── Shoulder width / hip width ratio ──
    if all(p is not None for p in [l_shoulder, r_shoulder, l_hip, r_hip]):
        shoulder_w = abs(r_shoulder.x - l_shoulder.x)
        hip_w      = abs(r_hip.x - l_hip.x)
        if hip_w > 0:
            metrics.shoulder_width_ratio = round(shoulder_w / hip_w, 3)

    metrics.warnings = warnings
    return metrics


def _compute_side_metrics(lm: dict[str, Point2D]) -> PostureMetrics:
    """
    Calculates metrics for left or right profile photos.
    Sagittal plane: head forward tilt and torso lean.
    """
    metrics = PostureMetrics(photo_angle="left")
    warnings: list[str] = []

    nose      = lm.get("NOSE")
    l_shoulder = lm.get("LEFT_SHOULDER")
    r_shoulder = lm.get("RIGHT_SHOULDER")
    l_hip      = lm.get("LEFT_HIP")
    r_hip      = lm.get("RIGHT_HIP")

    # Select the shoulder/hip side that is more visible in profile view
    shoulder = l_shoulder if (l_shoulder and l_shoulder.visibility > (r_shoulder.visibility if r_shoulder else 0)) else r_shoulder
    hip      = l_hip      if (l_hip      and l_hip.visibility      > (r_hip.visibility      if r_hip      else 0)) else r_hip

    # ── Head forward tilt (Forward Head Posture) ──
    if nose and shoulder and _min_visibility([nose, shoulder], threshold=0.4):
        # Difference between nose x and shoulder x → forward extension
        dx = nose.x - shoulder.x           # normalized coordinate
        dy = shoulder.y - nose.y           # positive since shoulder is below ear level
        head_forward = math.degrees(math.atan2(abs(dx), abs(dy))) if dy > 0 else 0.0
        metrics.head_forward_deg = round(head_forward, 2)
        if head_forward > 15:
            warnings.append(
                f"Significant head forward tilt ({head_forward:.1f}°). "
                "Strain on neck muscles and risk of cervical disc herniation."
            )
        elif head_forward > 8:
            warnings.append(f"Slight head forward tilt ({head_forward:.1f}°).")

    # ── Torso lean ──
    if shoulder and hip and _min_visibility([shoulder, hip], threshold=0.4):
        torso_lean = _angle_from_vertical(shoulder, hip)
        metrics.torso_lean_deg = round(torso_lean, 2)
        if torso_lean > 12:
            warnings.append(
                f"High torso forward lean ({torso_lean:.1f}°). "
                "Possible core muscle weakness or lumbar herniation posture."
            )

    metrics.warnings = warnings
    return metrics


# ─── Score Calculation ────────────────────────────────────────────────────────

def _calculate_posture_score(metrics: PostureMetrics) -> float:
    """
    Generates a score between 0–100 from weighted average of metrics.

    Weights:
      - Shoulder tilt:      30%
      - Hip tilt:           25%
      - Spine lateral:      25%
      - Head forward tilt:  15%
      - Torso lean:          5%
    """
    scores: list[tuple[float, float]] = []  # (score, weight)

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

    # Normalize weights of available metrics
    total_weight = sum(w for _, w in scores)
    weighted_sum = sum(s * w for s, w in scores)
    return round(weighted_sum / total_weight, 1)


# ─── Main Function ────────────────────────────────────────────────────────────

def analyze_posture(
    image_source: bytes | str | Path,
    photo_angle: str = "front",
    return_annotated: bool = True,
) -> PostureResult:
    """
    Performs posture analysis on a single photograph.

    Args:
        image_source: Raw bytes (multipart upload) or file path.
        photo_angle:  "front" | "back" | "left" | "right"
        return_annotated: If True, returns the annotated image (for preview).

    Returns:
        PostureResult — Can be directly saved to DB with .to_db_dict().

    Example usage (inside main.py):
        result = analyze_posture(await file.read(), photo_angle="front")
        if result.success:
            score = result.posture_score
            db_data = result.to_db_dict()
    """
    # ── Load image ──
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

    # ── Preprocess image ──
    # Cap long edge to 1024px (speed/accuracy balance)
    h, w = image_bgr.shape[:2]
    max_dim = 1024
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        image_bgr = cv2.resize(image_bgr, (int(w * scale), int(h * scale)))

    # ── MediaPipe detection ──
    detector = get_detector()
    detected, lm_dict, annotated = detector.detect(image_bgr)

    if not detected:
        return PostureResult(
            success=False,
            photo_angle=photo_angle,
            posture_score=0.0,
            metrics=PostureMetrics(
                photo_angle=photo_angle,
                warnings=["Human pose could not be detected in the photo. "
                          "Please upload a well-lit photo showing the full body."]
            ),
            landmarks_raw={},
            error_message="Pose detection failed.",
        )

    # Average visibility → detection confidence
    detection_confidence = round(
        sum(p.visibility for p in lm_dict.values()) / len(lm_dict), 3
    )

    # ── Calculate metrics based on angle ──
    if photo_angle in ("front", "back"):
        metrics = _compute_front_back_metrics(lm_dict)
        metrics.photo_angle = photo_angle
    else:  # left, right
        metrics = _compute_side_metrics(lm_dict)
        metrics.photo_angle = photo_angle

    metrics.detection_confidence = detection_confidence

    # ── Calculate score ──
    score = _calculate_posture_score(metrics)

    # ── Annotated image (optional) ──
    annotated_bytes: Optional[bytes] = None
    if return_annotated:
        success_enc, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if success_enc:
            annotated_bytes = buffer.tobytes()

    # ── Serialize landmarks ──
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
    Performs posture analysis from multiple angles and combines the results.

    Args:
        photos: {"front": <bytes>, "left": <bytes>, ...}

    Returns:
        {"front": PostureResult, "left": PostureResult, ...}

    Usage (inside main.py):
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
    Generates a single overall posture score from multi-angle analysis.

    Weights:
      front → 40%, back → 25%, left → 20%, right → 15%
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