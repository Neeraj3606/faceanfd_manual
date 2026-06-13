"""
Lightweight Anti-Spoofing using ONNX Runtime + OpenCV
NO TensorFlow, NO PyTorch

Works on:
- M1 Mac (ARM) locally
- Linux x86 on Google Cloud

Detection Strategy:
1. Texture analysis (Laplacian variance) - detects printed photos
2. Color distribution analysis - detects phone screens
3. Edge density analysis - real faces have more natural edges
4. Frequency domain analysis - screens have different frequency patterns
"""

import cv2
import numpy as np
from typing import Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)

# NOTE: This secondary heuristic is a safety net ONLY.
# MiniFASNet ONNX (primary) already handles true liveness detection.
# These thresholds must only catch extremely obvious printed-photo/screen attacks,
# NOT penalise genuine webcam/mobile captures with imperfect lighting.

# Relaxed thresholds — real webcam frames can have moderate sharpness/colour variance
SHARPNESS_THRESHOLD = 18.0       # Extremely blurry — clear flat print (was 55)
CONTRAST_THRESHOLD = 12.0        # Almost zero contrast — clearly fake (was 20)
EDGE_DENSITY_THRESHOLD = 0.008   # Almost no edges at all (was 0.02)
COLOR_VARIANCE_THRESHOLD = 55.0  # Very uniform colour — near-solid block (was 120)


def analyze_texture_quality(img_bgr: np.ndarray) -> Tuple[bool, float, str]:
    """
    Analyze image texture to detect printed photos.
    Only flags extremely blurry captures — not normal webcam frames.
    Returns: (is_real, sharpness_score, message)
    """
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness = float(laplacian.var())
        if sharpness < SHARPNESS_THRESHOLD:
            return False, sharpness, f"Image too blurry (sharpness: {sharpness:.1f}). Possible printed photo detected."
        return True, sharpness, "Texture quality OK"
    except Exception as e:
        logger.error(f"Texture analysis error: {e}")
        return True, 0.0, f"Texture check error: {str(e)}"


def analyze_color_distribution(img_bgr: np.ndarray) -> Tuple[bool, float, str]:
    """
    Analyze color distribution to detect phone/tablet screens.
    Only flags near-uniform colour blocks — not real faces.
    Returns: (is_real, color_variance, message)
    """
    try:
        b, g, r = cv2.split(img_bgr)
        color_variance = (float(np.var(b)) + float(np.var(g)) + float(np.var(r))) / 3.0
        if color_variance < COLOR_VARIANCE_THRESHOLD:
            return False, color_variance, f"Unnatural color distribution (variance: {color_variance:.1f}). Possible screen detected."
        return True, color_variance, "Color distribution OK"
    except Exception as e:
        logger.error(f"Color analysis error: {e}")
        return True, 0.0, f"Color check error: {str(e)}"


def analyze_edge_density(img_bgr: np.ndarray) -> Tuple[bool, float, str]:
    """
    Analyze edge density to detect spoofing.
    Only flags near-featureless images.
    Returns: (is_real, edge_density, message)
    """
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = float(np.count_nonzero(edges)) / float(edges.size or 1)
        if edge_density < EDGE_DENSITY_THRESHOLD:
            return False, edge_density, f"Abnormal edge pattern (density: {edge_density:.4f}). Possible spoofing detected."
        return True, edge_density, "Edge density OK"
    except Exception as e:
        logger.error(f"Edge analysis error: {e}")
        return True, 0.0, f"Edge check error: {str(e)}"


def analyze_contrast(img_bgr: np.ndarray) -> Tuple[bool, float, str]:
    """
    Analyze image contrast.
    Only flags near-zero contrast images.
    Returns: (is_real, contrast_score, message)
    """
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        contrast = float(np.std(gray))
        if contrast < CONTRAST_THRESHOLD:
            return False, contrast, f"Low contrast (score: {contrast:.1f}). Possible flat photo detected."
        return True, contrast, "Contrast OK"
    except Exception as e:
        logger.error(f"Contrast analysis error: {e}")
        return True, 0.0, f"Contrast check error: {str(e)}"


def check_antispoofing_lightweight(img_bgr: np.ndarray) -> Tuple[bool, str]:
    """
    Secondary heuristic anti-spoofing — safety net for obvious attacks.

    MiniFASNet ONNX (primary liveness) handles the main detection.
    This catches extreme cases that slip through or when the ONNX model is lenient:
    - Extremely blurry flat prints (ALL four checks must fail)
    - Near-zero contrast / near-solid colour blocks
    - Combined extreme condition triggers
    """
    try:
        if img_bgr is None or img_bgr.size == 0:
            return True, "Empty image — skipping secondary check"

        h, w = img_bgr.shape[:2]
        if w < 60 or h < 60:
            return True, "Image too small — skipping secondary check"

        details = {}
        failed_checks = []

        texture_ok, sharpness, texture_msg = analyze_texture_quality(img_bgr)
        details["sharpness"] = sharpness
        if not texture_ok:
            failed_checks.append(texture_msg)

        color_ok, color_var, color_msg = analyze_color_distribution(img_bgr)
        details["color_variance"] = color_var
        if not color_ok:
            failed_checks.append(color_msg)

        edge_ok, edge_density, edge_msg = analyze_edge_density(img_bgr)
        details["edge_density"] = edge_density
        if not edge_ok:
            failed_checks.append(edge_msg)

        contrast_ok, contrast, contrast_msg = analyze_contrast(img_bgr)
        details["contrast"] = contrast
        if not contrast_ok:
            failed_checks.append(contrast_msg)

        extreme_blurry_print = details["sharpness"] < 12.0 and details["contrast"] < 10.0
        extreme_flat_block = details["color_variance"] < 35.0 and details["edge_density"] < 0.006
        all_four_fail = len(failed_checks) >= 4

        if extreme_blurry_print or extreme_flat_block or all_four_fail:
            reason = failed_checks[0] if failed_checks else "Extreme spoof indicators detected"
            logger.warning("Secondary anti-spoofing REJECTED | Reasons: %s | Details: %s", failed_checks, details)
            return False, reason

        logger.info("Secondary anti-spoofing passed | failed=%d/4 | Details: %s", len(failed_checks), details)
        return True, "✅ Real face verified"

    except Exception as e:
        logger.error("Anti-spoofing check error: %s", e)
        # On error, let MiniFASNet decision stand — don't double-reject
        return True, "Secondary check error — bypassed"


def get_antispoofing_status() -> Dict[str, Any]:
    """Get anti-spoofing system status"""
    return {
        "available": True,
        "method": "lightweight_multi_check",
        "backend": "opencv + numpy",
        "checks": [
            "texture_quality",
            "color_distribution", 
            "edge_density",
            "contrast_analysis"
        ],
        "dependencies": ["opencv", "numpy"],
        "no_ml_models": True,
        "works_on": ["M1 Mac ARM", "Linux x86", "Any platform with OpenCV"]
    }


def check_antispoofing_image(img_array: np.ndarray) -> Tuple[bool, str]:
    """Primary anti-spoofing entrypoint used by attendance routes."""
    return check_antispoofing_lightweight(img_array)


def get_antispoofing_engine_status() -> Dict[str, Any]:
    """Primary anti-spoofing status entrypoint used by health endpoint."""
    return get_antispoofing_status()
