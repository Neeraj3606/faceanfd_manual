"""
Storage layer for Face Attendance Service

Responsibilities:
✔ create required folders
✔ load encodings cache
✔ save encodings cache

NO face recognition logic here
Only file operations
"""

import os
import pickle

from app.config import UPLOADS_DIR, DATA_DIR, ENCODINGS_FILE, MODEL_DIR


# ==============================
# Directory setup
# ==============================
def ensure_dirs():
    """
    Ensure required folders exist
    """
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)


# ==============================
# Cache Handling
# ==============================
def load_cache() -> dict:
    """
    Load encodings cache from file

    Structure:
    {
        "students": {
            student_id: {
                "name": str,
                "encodings": [np.array, ...]
            }
        }
    }
    """
    ensure_dirs()

    if not os.path.exists(ENCODINGS_FILE):
        return {"students": {}}

    with open(ENCODINGS_FILE, "rb") as f:
        return pickle.load(f)


def save_cache(cache: dict):
    """
    Save encodings cache to file
    """
    ensure_dirs()

    with open(ENCODINGS_FILE, "wb") as f:
        pickle.dump(cache, f)
