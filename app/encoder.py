"""
Face recognition — YuNet + SFace ONNX pipeline.

Replaces: InsightFace buffalo_l (325 MB, non-commercial)
With:
  Detection:   YuNet ONNX  (~390 KB, MIT — OpenCV Zoo)
  Recognition: SFace ONNX  (~37 KB,  MIT — OpenCV Zoo)
  Anti-spoof:  MiniFASNet   (~1.7 MB, Apache 2.0) [app/liveness.py — unchanged]

Commercially free. CPU-only. No PyTorch, no TensorFlow.
Same public API as the old InsightFace encoder — routes.py unchanged.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

# ── env setup (same as before) ────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MPLCONFIGDIR = os.path.join(_PROJECT_ROOT, "data", "matplotlib")
os.environ.setdefault("MPLCONFIGDIR", _MPLCONFIGDIR)
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
try:
    os.makedirs(_MPLCONFIGDIR, exist_ok=True)
except Exception:
    pass

from app.config import (
    ALLOWED_EXTENSIONS,
    DETECTION_MODEL_PATH,
    FACE_MODEL_TAG,
    INSIGHTFACE_DET_SIZE,
    RECOGNITION_MODEL_PATH,
    UPLOADS_DIR,
)

# Public flag — always True (pure ONNX, no heavy install required)
FACE_RECOGNITION_AVAILABLE: bool = True
_IMPORT_ERROR: Optional[str] = None

MAX_WIDTH = 640

# Lazy-initialised OpenCV model handles
_detector: Optional[cv2.FaceDetectorYN] = None
_recognizer: Optional[cv2.FaceRecognizerSF] = None
_FACE_APP_ERROR: Optional[str] = None


# ── Minimal face object ────────────────────────────────────────────────────────
class _FaceObj:
    """
    Drop-in replacement for InsightFace face object.
    .bbox  → [x1, y1, x2, y2]  used by liveness.py (check_liveness)
    .kps   → ndarray (5,2)      used by blink_detection.py (check_eyes_open)
             YuNet order: [right_eye, left_eye, nose, right_mouth, left_mouth]
             blink_detection only checks eyes-above-nose, so order is fine.
    .normed_embedding → set after recognition step
    """

    __slots__ = ("bbox", "kps", "det_score", "normed_embedding")

    def __init__(
        self,
        bbox: np.ndarray,       # [x1, y1, x2, y2]
        kps: np.ndarray,        # (5, 2)
        score: float,
    ) -> None:
        self.bbox = bbox.astype(np.float32)
        self.kps = kps.astype(np.float32)
        self.det_score = float(score)
        self.normed_embedding: Optional[np.ndarray] = None


# ── Model initialisation ───────────────────────────────────────────────────────
def get_face_app() -> Tuple[cv2.FaceDetectorYN, cv2.FaceRecognizerSF]:
    """Return (detector, recognizer), initialised lazily. Raises on failure."""
    global _detector, _recognizer, _FACE_APP_ERROR

    if _detector is not None and _recognizer is not None:
        return _detector, _recognizer

    missing = []
    if not os.path.exists(DETECTION_MODEL_PATH):
        missing.append(f"YuNet: {DETECTION_MODEL_PATH}")
    if not os.path.exists(RECOGNITION_MODEL_PATH):
        missing.append(f"SFace: {RECOGNITION_MODEL_PATH}")
    if missing:
        raise FileNotFoundError(
            "Face model(s) not found:\n  " + "\n  ".join(missing) +
            "\nRun:  python download_model.py"
        )

    try:
        _detector = cv2.FaceDetectorYN.create(
            DETECTION_MODEL_PATH,
            "",
            INSIGHTFACE_DET_SIZE,   # (320, 320) from config
            score_threshold=0.55,
            nms_threshold=0.3,
            top_k=100,
        )
        _recognizer = cv2.FaceRecognizerSF.create(
            RECOGNITION_MODEL_PATH, ""
        )
        _FACE_APP_ERROR = None
        return _detector, _recognizer
    except Exception as exc:
        _FACE_APP_ERROR = str(exc)
        raise RuntimeError(f"Face model init failed: {_FACE_APP_ERROR}") from exc


def get_face_engine_status(init: bool = False) -> dict:
    status = {
        "engine": "YuNet + SFace (OpenCV DNN / ONNX)",
        "detection_model": os.path.basename(DETECTION_MODEL_PATH),
        "recognition_model": os.path.basename(RECOGNITION_MODEL_PATH),
        "model_tag": FACE_MODEL_TAG,
        "dependency_available": FACE_RECOGNITION_AVAILABLE,
        "ready": _detector is not None and _recognizer is not None,
        "detection_model_exists": os.path.exists(DETECTION_MODEL_PATH),
        "recognition_model_exists": os.path.exists(RECOGNITION_MODEL_PATH),
        "license": "MIT (OpenCV Zoo)",
        "commercial_use": True,
        "error": _IMPORT_ERROR or _FACE_APP_ERROR,
    }
    if init:
        try:
            get_face_app()
            status["ready"] = True
            status["error"] = None
        except Exception as exc:
            status["ready"] = False
            status["error"] = str(exc)
    return status


# ── Image helpers ──────────────────────────────────────────────────────────────
def _resize_if_needed(img_bgr: np.ndarray) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    if w <= MAX_WIDTH:
        return img_bgr
    scale = MAX_WIDTH / float(w)
    return cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def load_image_safe(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    img = _resize_if_needed(img)
    return np.ascontiguousarray(img.astype(np.uint8))


def list_student_images(student_id: str) -> List[str]:
    """Legacy flat-folder image listing (kept for compatibility)."""
    folder = os.path.join(UPLOADS_DIR, str(student_id))
    if not os.path.isdir(folder):
        return []
    files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(ALLOWED_EXTENSIONS)
    ]
    files.sort()
    return files


# ── YuNet row → _FaceObj ───────────────────────────────────────────────────────
def _row_to_face(row: np.ndarray) -> _FaceObj:
    """
    YuNet row layout (15 values):
      [x, y, w, h,
       re_x, re_y,   ← right eye
       le_x, le_y,   ← left eye
       nt_x, nt_y,   ← nose tip
       rm_x, rm_y,   ← right mouth corner
       lm_x, lm_y,   ← left mouth corner
       score]
    """
    x, y, w, h = row[0], row[1], row[2], row[3]
    bbox = np.array([x, y, x + w, y + h], dtype=np.float32)
    kps = row[4:14].reshape(5, 2)  # 5 × (x, y)
    score = float(row[14])
    return _FaceObj(bbox, kps, score)


# ── Core detection ─────────────────────────────────────────────────────────────
def detect_faces(image_bgr: np.ndarray) -> List[_FaceObj]:
    """Detect all faces. Returns list of _FaceObj sorted by confidence desc."""
    det, _ = get_face_app()
    h, w = image_bgr.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(image_bgr)
    if faces is None or len(faces) == 0:
        return []
    faces_sorted = faces[np.argsort(-faces[:, 14])]  # sort by score desc
    return [_row_to_face(r) for r in faces_sorted]


def get_single_face(image_bgr: np.ndarray) -> Tuple[Optional[_FaceObj], str]:
    try:
        faces = detect_faces(image_bgr)
    except Exception as exc:
        return None, str(exc)

    if len(faces) == 0:
        return None, "No face detected."
    if len(faces) > 1:
        return None, "Multiple faces detected. Keep exactly one face in the frame."
    return faces[0], ""


# ── SFace recognition ──────────────────────────────────────────────────────────
def _get_embedding(image_bgr: np.ndarray, face_obj: _FaceObj) -> Optional[np.ndarray]:
    """
    Align-crop the face using YuNet bbox+kps, then run SFace.
    Returns L2-normalised 128-dim embedding, or None on failure.
    """
    _, rec = get_face_app()

    # Rebuild the YuNet face row expected by alignCrop:
    # [x, y, w, h, kp0..kp4 (10 values), score]
    x1, y1, x2, y2 = face_obj.bbox
    w = x2 - x1
    h = y2 - y1
    kps_flat = face_obj.kps.reshape(-1)          # 10 values
    face_row = np.array(
        [x1, y1, w, h, *kps_flat, face_obj.det_score],
        dtype=np.float32,
    ).reshape(1, -1)

    try:
        aligned = rec.alignCrop(image_bgr, face_row)
        raw_feat = rec.feature(aligned)           # (1, 128) or (128,)
        feat = np.asarray(raw_feat, dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(feat)
        if norm == 0:
            return None
        return feat / norm                         # L2-normalised
    except Exception as exc:
        import logging
        logging.getLogger(__name__).debug("SFace feature error: %s", exc)
        return None


def _embedding_from_face(face: _FaceObj) -> Optional[np.ndarray]:
    return face.normed_embedding


# ── Public API (same as old InsightFace encoder) ───────────────────────────────
def get_single_face_embedding(
    image_bgr: np.ndarray,
) -> Tuple[Optional[np.ndarray], Optional[_FaceObj], str]:
    """
    Detect one face and return (embedding, face_obj, message).
    face_obj has .bbox and .kps for downstream liveness / eye checks.
    """
    face, message = get_single_face(image_bgr)
    if face is None:
        return None, None, message

    embedding = _get_embedding(image_bgr, face)
    if embedding is None:
        return None, face, "Could not generate face embedding."

    face.normed_embedding = embedding
    return embedding, face, ""


def encode_single_image(image_bgr: np.ndarray) -> Optional[np.ndarray]:
    embedding, _, _ = get_single_face_embedding(image_bgr)
    return embedding


def encode_images_from_paths(paths: List[str]) -> List[np.ndarray]:
    """
    Generate SFace embeddings from multiple images.
    Bad files, zero-face and multi-face images are skipped.
    """
    final_encodings: List[np.ndarray] = []
    for path in paths:
        try:
            img = load_image_safe(path)
            enc = encode_single_image(img)
            if enc is not None:
                final_encodings.append(enc)
        except Exception:
            continue
    return final_encodings
