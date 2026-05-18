"""
MiniFASNet ONNX anti-spoofing — fully local inference, ONNX runtime only.

The attendance route calls this before face matching.
- By default the check FAILS CLOSED: if the model is missing, attendance is rejected.
- Multi-scale inference: runs on 2 crop scales, takes the max real score.
  This is significantly more robust on mobile cameras and partial face frames.
- Zero cloud API calls. Zero external network. Pure ONNX Runtime CPU inference.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

try:
    import onnxruntime as ort
    ONNXRUNTIME_AVAILABLE = True
    _IMPORT_ERROR: Optional[str] = None
except Exception as exc:
    ort = None
    ONNXRUNTIME_AVAILABLE = False
    _IMPORT_ERROR = str(exc)

from app.config import (
    LIVENESS_ENABLED,
    LIVENESS_FAIL_CLOSED,
    LIVENESS_COLOR_ORDER,
    LIVENESS_CROP_SCALE,
    LIVENESS_INPUT_SCALE,
    LIVENESS_REAL_CLASS_INDEX,
    LIVENESS_REAL_THRESHOLD,
    LIVENESS_MULTI_SCALE,
    LIVENESS_SCALES,
    SPOOF_MODEL_PATH,
)

logger = logging.getLogger(__name__)


@dataclass
class LivenessResult:
    is_real: bool
    message: str
    score: Optional[float] = None
    available: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "is_real": self.is_real,
            "message": self.message,
            "score": round(self.score, 4) if self.score is not None else None,
            "available": self.available,
            "reason": self.reason,
        }


_SESSION = None
_SESSION_ERROR: Optional[str] = None
_INPUT_NAME: Optional[str] = None
_INPUT_SHAPE: Optional[Sequence] = None


def _dim(value, fallback: int) -> int:
    return value if isinstance(value, int) and value > 0 else fallback


def _layout_and_size(shape: Optional[Sequence]) -> Tuple[str, int, int]:
    if not shape or len(shape) != 4:
        return "NCHW", 80, 80

    if shape[1] == 3:
        return "NCHW", _dim(shape[2], 80), _dim(shape[3], 80)
    if shape[3] == 3:
        return "NHWC", _dim(shape[1], 80), _dim(shape[2], 80)
    return "NCHW", 80, 80


def get_liveness_session():
    global _SESSION, _SESSION_ERROR, _INPUT_NAME, _INPUT_SHAPE

    if not LIVENESS_ENABLED:
        return None
    if not ONNXRUNTIME_AVAILABLE or ort is None:
        raise RuntimeError(f"onnxruntime import failed: {_IMPORT_ERROR or 'not installed'}")
    if not os.path.exists(SPOOF_MODEL_PATH):
        raise FileNotFoundError(
            f"MiniFASNet ONNX model not found at: {SPOOF_MODEL_PATH}\n"
            f"Run: python download_model.py  to download it automatically."
        )

    if _SESSION is not None:
        return _SESSION

    try:
        _SESSION = ort.InferenceSession(
            SPOOF_MODEL_PATH,
            providers=["CPUExecutionProvider"],
        )
        model_input = _SESSION.get_inputs()[0]
        _INPUT_NAME = model_input.name
        _INPUT_SHAPE = model_input.shape
        _SESSION_ERROR = None
        logger.info("MiniFASNet ONNX session loaded successfully (CPU). Shape: %s", _INPUT_SHAPE)
        return _SESSION
    except Exception as exc:
        _SESSION_ERROR = str(exc)
        raise RuntimeError(f"MiniFASNet model is not ready: {_SESSION_ERROR}") from exc


def get_liveness_status(init: bool = False) -> dict:
    status = {
        "enabled": LIVENESS_ENABLED,
        "engine": "MiniFASNet ONNX (local CPU only)",
        "model_path": SPOOF_MODEL_PATH,
        "dependency_available": ONNXRUNTIME_AVAILABLE,
        "model_exists": os.path.exists(SPOOF_MODEL_PATH),
        "fail_closed": LIVENESS_FAIL_CLOSED,
        "multi_scale": LIVENESS_MULTI_SCALE,
        "scales": LIVENESS_SCALES,
        "ready": _SESSION is not None or not LIVENESS_ENABLED,
        "error": _IMPORT_ERROR or _SESSION_ERROR,
        "real_class_index": LIVENESS_REAL_CLASS_INDEX,
        "real_threshold": LIVENESS_REAL_THRESHOLD,
        "input_scale": LIVENESS_INPUT_SCALE,
        "color_order": LIVENESS_COLOR_ORDER,
        "crop_scale": LIVENESS_CROP_SCALE,
    }

    if init and LIVENESS_ENABLED:
        try:
            get_liveness_session()
            status["ready"] = True
            status["error"] = None
        except Exception as exc:
            status["ready"] = False
            status["error"] = str(exc)
            logger.warning("Liveness init failed: %s", exc)

    return status


def _fail_or_bypass(message: str, reason: str) -> LivenessResult:
    if LIVENESS_FAIL_CLOSED:
        logger.warning("Liveness fail-closed triggered: %s | reason=%s", message, reason)
        return LivenessResult(False, message, available=False, reason=reason)
    return LivenessResult(
        True,
        "Liveness check unavailable; bypassed by configuration.",
        available=False,
        reason=reason,
    )


def _crop_face(frame_bgr: np.ndarray, bbox: Sequence[float], scale: float) -> Optional[np.ndarray]:
    """Crop face region with configurable scale around the bounding box center."""
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in bbox[:4]]
    bw = max(0, x2 - x1)
    bh = max(0, y2 - y1)
    if bw < 20 or bh < 20:
        return None

    cx = x1 + bw / 2.0
    cy = y1 + bh / 2.0
    scaled_w = bw * scale
    scaled_h = bh * scale
    x1 = max(0, int(round(cx - scaled_w / 2.0)))
    y1 = max(0, int(round(cy - scaled_h / 2.0)))
    x2 = min(w, int(round(cx + scaled_w / 2.0)))
    y2 = min(h, int(round(cy + scaled_h / 2.0)))

    if x2 <= x1 or y2 <= y1:
        return None
    return frame_bgr[y1:y2, x1:x2]


def _prepare_input(crop_bgr: np.ndarray) -> np.ndarray:
    """Resize, optionally convert color order, normalize, and batch the crop."""
    layout, height, width = _layout_and_size(_INPUT_SHAPE)
    resized = cv2.resize(crop_bgr, (width, height), interpolation=cv2.INTER_LINEAR)
    image = resized if LIVENESS_COLOR_ORDER == "bgr" else cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    image = image.astype(np.float32)

    if LIVENESS_INPUT_SCALE == "0_1":
        image = image / 255.0
    elif LIVENESS_INPUT_SCALE == "minus1_1":
        image = (image - 127.5) / 128.0
    # "0_255": leave as-is

    if layout == "NCHW":
        image = np.transpose(image, (2, 0, 1))

    return np.expand_dims(image, axis=0).astype(np.float32)


def _probabilities(raw_output: np.ndarray) -> np.ndarray:
    """Convert raw model output to probabilities via softmax if needed."""
    scores = np.asarray(raw_output, dtype=np.float32).reshape(-1)
    if scores.size == 0:
        return scores

    if scores.size == 1:
        value = float(scores[0])
        if not 0.0 <= value <= 1.0:
            value = 1.0 / (1.0 + np.exp(-value))
        return np.asarray([value], dtype=np.float32)

    # Already probabilities (sum ≈ 1)?
    if np.all(scores >= 0) and abs(float(np.sum(scores)) - 1.0) < 0.03:
        return scores

    # Apply softmax
    scores = scores - np.max(scores)
    exp = np.exp(scores)
    return exp / np.sum(exp)


def _run_single_crop(session, crop_bgr: np.ndarray) -> Optional[float]:
    """Run inference on one crop. Returns the real-class probability or None on failure."""
    input_blob = _prepare_input(crop_bgr)
    try:
        output = session.run(None, {_INPUT_NAME: input_blob})[0]
    except Exception as exc:
        logger.debug("MiniFASNet inference error on crop: %s", exc)
        return None

    probs = _probabilities(output)
    if probs.size == 0:
        return None

    real_index = min(max(LIVENESS_REAL_CLASS_INDEX, 0), probs.size - 1)
    return float(probs[real_index])


def _check_texture_quality(crop_bgr: np.ndarray) -> Tuple[bool, float]:
    """
    Simple texture analysis to detect obvious printed photos or screen displays.
    Returns (is_suspicious, quality_score)
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return False, 1.0
    
    try:
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.count_nonzero(edges)) / float(edges.size or 1)

        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
        sat_mean = float(np.mean(hsv[:, :, 1]))
        val = hsv[:, :, 2]
        highlight_ratio = float(np.mean(val > 240))

        # Weighted quality score (higher is better/live-like)
        q_sharp = min(1.0, laplacian_var / 180.0)
        q_edges = min(1.0, edge_density / 0.09)
        q_sat = min(1.0, sat_mean / 55.0)
        q_glare = max(0.0, 1.0 - (highlight_ratio / 0.18))
        quality = max(0.0, min(1.0, (0.4 * q_sharp) + (0.25 * q_edges) + (0.2 * q_sat) + (0.15 * q_glare)))

        suspicious = False
        if laplacian_var < 22.0:
            suspicious = True
        if edge_density < 0.02:
            suspicious = True
        if sat_mean < 28.0 and highlight_ratio > 0.08:
            suspicious = True

        return suspicious, quality
    except Exception:
        # Fail-safe: if texture analysis fails, don't auto-pass as perfect.
        return True, 0.35


def check_liveness(frame_bgr: np.ndarray, bbox: Sequence[float]) -> LivenessResult:
    """
    Check whether the face in `frame_bgr` is live or spoofed.

    Multi-scale strategy (LIVENESS_MULTI_SCALE=true):
      Run inference on N crop scales and take the MAXIMUM real score.
      If any scale says "real" at threshold, we accept. This reduces false rejections
      on slightly blurry or partially cropped mobile frames.
    """
    if not LIVENESS_ENABLED:
        return LivenessResult(True, "Liveness check disabled.", available=False, reason="disabled")

    try:
        session = get_liveness_session()
    except Exception as exc:
        return _fail_or_bypass(str(exc), "model_unavailable")

    # Determine which scales to run
    scales: List[float] = LIVENESS_SCALES if (LIVENESS_MULTI_SCALE and len(LIVENESS_SCALES) > 1) else [LIVENESS_CROP_SCALE]

    scores: List[float] = []
    best_crop = None
    best_real_score: Optional[float] = None

    for scale in scales:
        crop = _crop_face(frame_bgr, bbox, scale)
        if crop is None:
            continue
        score = _run_single_crop(session, crop)
        if score is None:
            continue
        scores.append(float(score))
        if best_real_score is None or score > best_real_score:
            best_real_score = score
            best_crop = crop

    if not scores:
        # No successful inference — could be face too small
        crop_check = _crop_face(frame_bgr, bbox, LIVENESS_CROP_SCALE)
        if crop_check is None:
            return LivenessResult(
                False,
                "Face is too small or too close to the edge. Move back a little.",
                available=True,
                reason="bad_crop",
            )
        return _fail_or_bypass("MiniFASNet inference failed on all scales.", "inference_failed")

    # Balanced multi-scale aggregation.
    # Use weighted combination of max and median to be robust across scales.
    # max_score captures if ANY scale clearly sees a live face.
    # median_score prevents a single lucky outlier from passing.
    scores_arr = np.asarray(scores, dtype=np.float32)
    median_score = float(np.median(scores_arr))
    min_score = float(np.min(scores_arr))
    max_score = float(np.max(scores_arr))
    score_spread = max_score - min_score

    # Weighted combined score: favours the best scale but anchors on median
    combined_score = float(max_score * 0.4 + median_score * 0.6)

    is_suspicious = False
    texture_quality = 1.0
    if best_crop is not None:
        is_suspicious, texture_quality = _check_texture_quality(best_crop)

    # Primary gate: combined_score must exceed threshold.
    # secondary gate: min_score must not be extremely low (catches 1-scale flukes).
    is_real = (
        combined_score >= LIVENESS_REAL_THRESHOLD
        and min_score >= (LIVENESS_REAL_THRESHOLD * 0.65)
    )

    # Texture/screen heuristic: only hard-reject if texture is VERY low
    # (printed A4 photo or clearly flat screen). Threshold lowered to 0.35
    # so real webcam/mobile faces with moderate saturation are not rejected.
    if is_suspicious and texture_quality < 0.35:
        is_real = False

    logger.info(
        "Liveness balanced: is_real=%s combined=%.4f median=%.4f min=%.4f max=%.4f spread=%.4f threshold=%.4f texture=%.4f suspicious=%s scales=%s",
        is_real, combined_score, median_score, min_score, max_score, score_spread,
        LIVENESS_REAL_THRESHOLD, texture_quality, is_suspicious, scales,
    )

    if is_real:
        return LivenessResult(True, "Live face verified.", score=combined_score, available=True)

    return LivenessResult(
        False,
        "Spoof detected. Please use your real face — photos and screens are not accepted.",
        score=combined_score,
        available=True,
        reason="spoof",
    )
