"""
Global configuration for Face Attendance Service

✔ All paths
✔ Thresholds
✔ Server settings
✔ Database config
✔ Centralized constants

If anything changes, edit ONLY this file.
"""

import os


# ==============================
# Project Paths
# ==============================

# app/ folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Face attendance/ (project root)
PROJECT_ROOT = os.path.dirname(BASE_DIR)


# ==============================
# Storage
# ==============================

# uploads/students/{school_name}/{class_name}/{section}/{student_id}/images
UPLOADS_DIR = os.path.join(PROJECT_ROOT, "uploads", "students")

# data/ folder for cache/logs
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# face embeddings cache file (pickle)
ENCODINGS_FILE = os.path.join(DATA_DIR, "encodings.pkl")

# ONNX model files
MODEL_DIR = os.path.join(DATA_DIR, "models")
SPOOF_MODEL_PATH = os.getenv(
    "MINIFASNET_ONNX_PATH",
    os.path.join(MODEL_DIR, "minifasnet_v2.onnx"),
)


# ==============================
# Database (SQLite only)
# ==============================
_sqlite_path = os.path.join(DATA_DIR, "attendance.db")
_db_env = (os.getenv("DATABASE_URL") or "").strip()
DB_URL = _db_env if _db_env else f"sqlite:///{_sqlite_path}"


# ==============================
# Face Recognition Settings - YuNet + SFace (OpenCV Zoo, MIT License)
# ==============================

# Minimum good photos required to enroll
MIN_ENROLL_PHOTOS = 8

# SFace cosine distance threshold: distance = 1 - cosine_similarity.
# SFace features are 128-dim normalized. 0.55-0.65 is a good range.
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.60"))

# Margin between best and second match
MATCH_MARGIN = 0.05

# YuNet face detection model (~390 KB, MIT - OpenCV Zoo)
DETECTION_MODEL_PATH = os.getenv(
    "YUNET_ONNX_PATH",
    os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx"),
)

# SFace face recognition model (~37 KB, MIT - OpenCV Zoo)
RECOGNITION_MODEL_PATH = os.getenv(
    "SFACE_ONNX_PATH",
    os.path.join(MODEL_DIR, "face_recognition_sface_2021dec.onnx"),
)

# Detection input size (width, height)
INSIGHTFACE_DET_SIZE = (
    int(os.getenv("DET_WIDTH", "320")),
    int(os.getenv("DET_HEIGHT", "320")),
)

FACE_MODEL_TAG = "yunet+sface:onnx_mit"


# ==============================
# Anti-Spoofing Settings - MiniFASNet ONNX
# ==============================

LIVENESS_ENABLED = os.getenv("LIVENESS_ENABLED", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}

# Fail closed keeps security strict. If the model is missing/unreadable, face attendance is rejected.
LIVENESS_FAIL_CLOSED = os.getenv("LIVENESS_FAIL_CLOSED", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
# Threshold lowered from 0.75 → 0.60 to avoid false rejections of real live faces.
# MiniFASNet scores vary by lighting/camera — 0.60 catches photos/screens while
# keeping genuine webcam/mobile captures accepted.
LIVENESS_REAL_THRESHOLD = float(os.getenv("MINIFASNET_REAL_THRESHOLD", "0.60"))
# MiniFASNet V2 outputs 3 classes: [spoof_print, REAL, spoof_replay]
# Real class is at index 1 when using 0-255 RGB input.
# CRITICAL: this model needs raw 0-255 pixel values in RGB order.
# With 0_1 normalization the model cannot discriminate real vs spoof at all.
LIVENESS_REAL_CLASS_INDEX = int(os.getenv("MINIFASNET_REAL_CLASS_INDEX", "1"))
# Crop scale 2.0 gives a moderate context around the face (not too tight, not too loose)
LIVENESS_CROP_SCALE = float(os.getenv("MINIFASNET_CROP_SCALE", "2.0"))

# MiniFASNet V2 requires RAW 0-255 pixel values — NOT normalized to [0,1].
# With 0_1 or minus1_1, the model sees near-zero input and scores everything the same.
# Must use 0_255 (no normalization). Color must be RGB (not BGR).
# Supported: 0_255, 0_1, minus1_1
LIVENESS_INPUT_SCALE = os.getenv("MINIFASNET_INPUT_SCALE", "0_255").strip().lower()
# Must be RGB for this model (tested: bgr gives wrong scores)
LIVENESS_COLOR_ORDER = os.getenv("MINIFASNET_COLOR_ORDER", "rgb").strip().lower()

# Multi-scale inference: run liveness on multiple crop scales and take max real score.
# More robust against partial face captures on mobile. Uses ONNX runtime only.
LIVENESS_MULTI_SCALE = os.getenv("MINIFASNET_MULTI_SCALE", "true").strip().lower() not in {
    "0", "false", "no", "off",
}
# Scales closer to face center — avoids background confusing MiniFASNet
LIVENESS_SCALES = [float(s) for s in os.getenv("MINIFASNET_SCALES", "1.5,2.0,2.5").split(",") if s.strip()]


# ==============================
# ✅ Server (NETWORK ACCESS)
# ==============================

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))


# ==============================
# Misc
# ==============================

ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png")
