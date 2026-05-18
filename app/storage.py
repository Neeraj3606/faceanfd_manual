"""
Storage layer for Face Attendance Service

Encodings are stored in SQLite DB (face_encodings table) so they
survive Render restarts and redeploys.
"""

import os
import pickle
import logging

from app.config import UPLOADS_DIR, DATA_DIR, ENCODINGS_FILE, MODEL_DIR

logger = logging.getLogger(__name__)


def ensure_dirs():
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)


def load_cache() -> dict:
    """
    Load encodings from DB (persistent across restarts).
    Falls back to pkl file if DB is empty.
    """
    ensure_dirs()

    try:
        from app.db import SessionLocal
        from app.models import FaceEncoding

        db = SessionLocal()
        try:
            rows = db.query(FaceEncoding).all()
            if rows:
                students = {}
                for row in rows:
                    try:
                        encoding = pickle.loads(row.encoding_blob)
                        if row.student_id not in students:
                            students[row.student_id] = {
                                "name": row.student_name,
                                "encodings": []
                            }
                        students[row.student_id]["encodings"].append(encoding)
                    except Exception as e:
                        print(f"Skipping bad encoding row {row.id}: {e}")
                        continue
                print(f"Loaded {len(students)} students from DB")
                return {"students": students}
        finally:
            db.close()
    except Exception as e:
        print(f"DB load failed, falling back to pkl: {e}")

    # Fallback: pkl file
    if os.path.exists(ENCODINGS_FILE):
        try:
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
                print("Loaded encodings from pkl file (fallback)")
                return data
        except Exception as e:
            print(f"pkl load failed: {e}")

    return {"students": {}}


def save_cache(cache: dict):
    """
    Save encodings to DB (persistent across restarts).
    """
    ensure_dirs()

    students = cache.get("students", {})

    try:
        from app.db import SessionLocal
        from app.models import FaceEncoding

        db = SessionLocal()
        try:
            db.query(FaceEncoding).delete()
            db.flush()

            for student_id, data in students.items():
                name = data.get("name", "")
                encodings = data.get("encodings", [])
                for enc in encodings:
                    try:
                        blob = pickle.dumps(enc)
                        row = FaceEncoding(
                            student_id=str(student_id),
                            student_name=str(name),
                            encoding_blob=blob,
                        )
                        db.add(row)
                    except Exception as e:
                        print(f"Skipping encoding for {student_id}: {e}")
                        continue

            db.commit()
            print(f"Saved {len(students)} students to DB")
        except Exception as e:
            db.rollback()
            print(f"SAVE ERROR (DB flush/commit failed): {e}")
            raise
        finally:
            db.close()
    except Exception as e:
        import traceback
        print(f"SAVE ERROR (General): {e}")
        traceback.print_exc()

    # pkl backup (local dev only)
    try:
        with open(ENCODINGS_FILE, "wb") as f:
            pickle.dump(cache, f)
    except Exception:
        pass
