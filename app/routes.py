"""
API Routes for Face Attendance Service

Responsibilities:
- Enroll / update students
- Manage student photos + encodings cache
- Mark attendance (IN/OUT)
- Export today's attendance CSV
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import os
import re
import shutil
from typing import List, Optional, Dict, Any

import cv2
import numpy as np

from fastapi import APIRouter, Depends, File, Form, UploadFile, Body
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.attendance_excel import export_today_attendance_excel, export_attendance_excel, generate_summary_excel

from app.config import (
    UPLOADS_DIR,
    ENCODINGS_FILE,
    FACE_MODEL_TAG,
    MIN_ENROLL_PHOTOS,
    ALLOWED_EXTENSIONS,
    MATCH_THRESHOLD,
)
from app.storage import ensure_dirs, load_cache, save_cache
from app.storage_helper import get_student_folder_path, ensure_student_folder, list_student_images_new
from app.encoder import (
    FACE_RECOGNITION_AVAILABLE,
    encode_images_from_paths,
    get_face_engine_status,
    get_single_face_embedding,
)
from app.liveness import check_liveness, get_liveness_status
from app.blink_detection import check_eyes_open
from app.antispoofing_onnx import check_antispoofing_image, get_antispoofing_engine_status
from app.db import get_db
from app.models import Attendance, Student, User
from app.auth import get_current_user, user_role, user_school

router = APIRouter()


def _student_visible_to_user(student: Student, current_user: User) -> bool:
    role = user_role(current_user)
    if role == "SUPER_ADMIN":
        return True
    if (student.school_name or "") != user_school(current_user):
        return False
    if role == "TEACHER":
        assigned_class = (getattr(current_user, "class_assigned", "") or "").strip()
        assigned_section = (getattr(current_user, "section_assigned", "") or "").strip()
        if assigned_class and (student.class_name or "").strip() != assigned_class:
            return False
        if assigned_section and (student.section or "").strip() != assigned_section:
            return False
    return True


def _apply_student_scope(query, current_user: User):
    role = user_role(current_user)
    if role == "SUPER_ADMIN":
        return query
    query = query.filter(Student.school_name == user_school(current_user))
    if role == "TEACHER":
        assigned_class = (getattr(current_user, "class_assigned", "") or "").strip()
        assigned_section = (getattr(current_user, "section_assigned", "") or "").strip()
        if assigned_class:
            query = query.filter(Student.class_name == assigned_class)
        if assigned_section:
            query = query.filter(Student.section == assigned_section)
    return query


def _normalize_student_code(student_id: str) -> str:
    return str(student_id or "").strip()


def _build_scoped_student_pk(school_name: str, student_code: str) -> str:
    scope = f"{(school_name or '').strip().lower()}|{(student_code or '').strip().lower()}"
    return "sid_" + hashlib.sha1(scope.encode("utf-8")).hexdigest()


def _display_student_id(student: Student) -> str:
    code = (getattr(student, "student_code", "") or "").strip()
    return code or (student.id or "")


def _find_scoped_student(
    db: Session,
    current_user: User,
    student_code: str,
    school_name: Optional[str] = None,
) -> Optional[Student]:
    code = _normalize_student_code(student_code)
    if not code:
        return None
    query = _apply_student_scope(db.query(Student), current_user)
    if school_name:
        query = query.filter(Student.school_name == school_name)
    return query.filter(or_(Student.student_code == code, Student.id == code)).first()


# =========================================================
# Helper: Identify from numpy image array
# =========================================================
def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 999.0
    similarity = float(np.dot(a, b) / denom)
    return 1.0 - similarity


def _crop_face_for_spoof_check(img_bgr: np.ndarray, bbox, pad_ratio: float = 0.18) -> Optional[np.ndarray]:
    """Crop a padded face ROI so anti-spoof checks run on face content, not full background."""
    if bbox is None:
        return None
    h, w = img_bgr.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in bbox[:4]]
    bw = max(0, x2 - x1)
    bh = max(0, y2 - y1)
    if bw < 20 or bh < 20:
        return None

    pad_x = int(round(bw * pad_ratio))
    pad_y = int(round(bh * pad_ratio))
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w, x2 + pad_x)
    y2 = min(h, y2 + pad_y)
    if x2 <= x1 or y2 <= y1:
        return None
    return img_bgr[y1:y2, x1:x2]


def identify_from_image_array(img_bgr: np.ndarray, students: Dict[str, Dict[str, Any]]):
    """Return (best_sid, best_name, best_distance, metadata)."""
    meta: Dict[str, Any] = {
        "message": None,
        "antispoofing": None,
        "compatible_embeddings": 0,
    }

    # Run anti-spoofing only on detected face ROI (not full frame) to avoid
    # false rejections from background/lighting artifacts.
    meta["antispoofing_light"] = None

    if not FACE_RECOGNITION_AVAILABLE:
        meta["message"] = "InsightFace is not installed."
        return None, None, None, meta

    face_encoding, face, message = get_single_face_embedding(img_bgr)
    if face_encoding is None or face is None:
        meta["message"] = message or "No usable face found."
        return None, None, None, meta

    bbox = getattr(face, "bbox", None)
    if bbox is None:
        meta["message"] = "Face detection bbox missing. Please recapture in good lighting."
        meta["spoof_rejected"] = True
        return None, None, None, meta

    # Primary anti-spoofing: MiniFASNet liveness on detected face bbox (fail-closed by config).
    liveness_result = check_liveness(img_bgr, bbox)
    meta["antispoofing"] = {
        "engine": "minifasnet_onnx",
        **liveness_result.to_dict(),
    }
    if not liveness_result.is_real:
        meta["message"] = liveness_result.message
        meta["spoof_rejected"] = True
        return None, None, None, meta

    # Secondary heuristic anti-spoofing to catch obvious printed/screen replays.
    # Important: run it on detected face ROI, not full frame.
    spoof_roi = _crop_face_for_spoof_check(img_bgr, bbox)
    if spoof_roi is None:
        meta["message"] = "Face crop invalid for anti-spoofing. Please recapture clearly."
        meta["spoof_rejected"] = True
        return None, None, None, meta
    is_real, spoof_message = check_antispoofing_image(spoof_roi)
    meta["antispoofing_light"] = {"is_real": is_real, "message": spoof_message}
    if not is_real:
        meta["message"] = "Spoofing detected"
        meta["spoof_rejected"] = True
        return None, None, None, meta

    # Extra check: reject clearly closed-eye static captures to reduce replay acceptance.
    eyes_open, eyes_msg = check_eyes_open(img_bgr, face)
    meta["eyes"] = {"open": eyes_open, "message": eyes_msg}
    if not eyes_open:
        meta["message"] = "Eyes must be open for live attendance capture."
        meta["spoof_rejected"] = True
        return None, None, None, meta

    probe = np.asarray(face_encoding, dtype=np.float32).reshape(-1)
    best_sid = None
    best_name = None
    best_distance = 999.0

    for sid, data in students.items():
        encodings = data.get("encodings", [])
        if not encodings:
            continue

        for known in encodings:
            known_arr = np.asarray(known, dtype=np.float32).reshape(-1)
            if known_arr.shape != probe.shape:
                continue

            meta["compatible_embeddings"] += 1
            d = _cosine_distance(known_arr, probe)
            if d < best_distance:
                best_distance = d
                best_sid = sid
                best_name = data.get("name", "")

    if meta["compatible_embeddings"] == 0:
        meta["message"] = "No compatible InsightFace enrollments found. Re-enroll students to rebuild embeddings."

    return best_sid, best_name, best_distance, meta


# ==============================
# Health
# ==============================
@router.get("/health")
def health():
    ensure_dirs()
    return {
        "ok": True,
        "service": "face-attendance",
        "message": "Server running",
        "recognition": get_face_engine_status(init=True),
        "liveness": get_liveness_status(init=True),
        "antispoofing": get_antispoofing_engine_status(),
        "uploads_dir": UPLOADS_DIR,
        "encodings_file": ENCODINGS_FILE,
    }


# ==============================
# Enroll / Update / Photo Update
# ==============================
@router.post("/enroll")
async def enroll(
    student_id: str = Form(...),
    name: str = Form(""),
    school_name: str = Form(""),
    class_name: str = Form(""),
    section: str = Form(""),
    roll: str = Form(""),
    replace_photos: str = Form("false"),
    files: List[UploadFile] = File([]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Single endpoint for:
    - New enroll (must include photos)
    - Update details only (no photos)
    - Update photos (optionally replace old photos)

    Important behavior:
    ✅ Partial update: blank fields NEVER wipe existing values.
    """

    ensure_dirs()

    student_code = _normalize_student_code(student_id)
    if not student_code:
        return {"ok": False, "message": "Student ID is required."}

    # Clean inputs
    name = (name or "").strip()
    school_name = (school_name or "").strip()
    class_name = (class_name or "").strip()
    section = (section or "").strip()
    roll = (roll or "").strip()
    role = user_role(current_user)
    if role == "TEACHER":
        school_name = user_school(current_user)
        assigned_class = (getattr(current_user, "class_assigned", "") or "").strip()
        assigned_section = (getattr(current_user, "section_assigned", "") or "").strip()
        if assigned_class:
            class_name = assigned_class
        if assigned_section:
            section = assigned_section
    elif role == "ADMIN":
        school_name = user_school(current_user)

    # Backward compatible: if class_name like "10-A" and section empty -> split
    if class_name and "-" in class_name and not section:
        parts = class_name.split("-", 1)
        class_name = parts[0].strip()
        section = parts[1].strip()

    effective_school = school_name or "MainSchool"
    if role == "SUPER_ADMIN" and not effective_school:
        effective_school = "MainSchool"

    # Existing student in scoped DB?
    student: Optional[Student] = _find_scoped_student(
        db=db,
        current_user=current_user,
        student_code=student_code,
        school_name=effective_school if role == "SUPER_ADMIN" else None,
    )
    if student:
        effective_school = student.school_name or effective_school or "MainSchool"
    internal_sid = student.id if student else _build_scoped_student_pk(effective_school, student_code)

    # Uploaded photos?
    has_files = bool(files)

    # replace flag normalize
    replace_flag = (replace_photos or "false").strip().lower() in ("1", "true", "yes", "y")

    # ------------------------------
    # CASE 1: Detail update only (no photos)
    # ------------------------------
    if student and not has_files:
        if name:
            student.name = name
        if class_name:
            student.class_name = class_name
        if section:
            student.section = section
        if roll:
            student.roll = roll
        db.commit()

        # Update cache name ONLY if name changed and student exists in cache
        if name:
            cache = load_cache()
            cache.setdefault("students", {})
            for cache_key in {student.id, _display_student_id(student)}:
                if cache_key and cache_key in cache["students"]:
                    cache["students"][cache_key]["name"] = student.name
            save_cache(cache)

        return {"ok": True, "message": "Student updated successfully"}

    # If new student & no photos -> allow basic enrollment (for existing school integration)
    if not student and not has_files:
        # Create basic student record without photos (for existing school integration)
        db.add(
            Student(
                id=internal_sid,
                student_code=student_code,
                name=name or "",
                school_name=effective_school,
                class_name=class_name or "",
                section=section or "",
                roll=roll or "",
            )
        )
        db.commit()
        
        return {"ok": True, "message": "Student enrolled successfully. Please add photos later for face recognition."}

    # ------------------------------
    # CASE 2: Photos provided (Enroll / Update Photos)
    # ------------------------------
    # Use effective school name with class/section structure
    folder_student_id = student_code
    if not folder_student_id and student:
        folder_student_id = _display_student_id(student)
    student_folder = ensure_student_folder(effective_school, class_name, section, folder_student_id)

    # If replace -> delete existing photos
    if has_files and replace_flag:
        try:
            for fn in os.listdir(student_folder):
                fp = os.path.join(student_folder, fn)
                if os.path.isfile(fp):
                    os.remove(fp)
        except Exception:
            pass

    # Next index (append mode)
    next_idx = 1
    if has_files and not replace_flag:
        try:
            existing = [
                f
                for f in os.listdir(student_folder)
                if f.lower().endswith(ALLOWED_EXTENSIONS)
            ]
        except Exception:
            existing = []

        if existing:
            mx = 0
            for fn in existing:
                m = re.search(r"img_(\d+)", fn)
                if m:
                    mx = max(mx, int(m.group(1)))
            next_idx = mx + 1

    # Save uploaded photos
    if len(files) > 0:
        for f in files:
            if not f.filename or not f.filename.strip():
                continue

            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue

            out_path = os.path.join(student_folder, f"img_{next_idx:03d}{ext}")
            with open(out_path, "wb") as out:
                out.write(await f.read())
            next_idx += 1

    face_status = get_face_engine_status(init=True)
    if not face_status.get("ready"):
        if student:
            student.name = name or student.name
            student.school_name = effective_school
            student.class_name = class_name or student.class_name
            student.section = section or student.section
            student.roll = roll or student.roll
        else:
            db.add(
                Student(
                    id=internal_sid,
                    student_code=student_code,
                    name=name,
                    school_name=effective_school,
                    class_name=class_name,
                    section=section,
                    roll=roll,
                )
            )
        db.commit()
        return {
            "ok": True,
            "message": f"Student saved. InsightFace is unavailable, so use manual attendance until it is ready. {face_status.get('error') or ''}".strip(),
        }

    # Build encodings from ALL images present
    image_paths = list_student_images_new(effective_school, class_name, section, folder_student_id)
    encodings = encode_images_from_paths(image_paths)

    if len(encodings) < MIN_ENROLL_PHOTOS:
        return {
            "ok": False,
            "message": f"Not enough valid photos. Need at least {MIN_ENROLL_PHOTOS}.",
        }

    # ✅ Prevent accidental wipe during photo update:
    if student:
        if not name:
            name = student.name or ""
        if not class_name:
            class_name = student.class_name or ""
        if not section:
            section = student.section or ""
        if not roll:
            roll = student.roll or ""

    # Save/Update DB roster first to avoid Foreign Key violations in save_cache
    if student:
        student.name = name
        student.school_name = effective_school
        student.class_name = class_name
        student.section = section
        student.roll = roll
        student.student_code = student_code
    else:
        db.add(
            Student(
                id=internal_sid,
                student_code=student_code,
                name=name,
                school_name=effective_school,
                class_name=class_name,
                section=section,
                roll=roll,
            )
        )
    db.commit()

    # Save to cache (encodings) AFTER student is in DB
    cache = load_cache()
    cache["model"] = FACE_MODEL_TAG
    cache.setdefault("students", {})
    cache["students"][internal_sid] = {"name": name, "encodings": encodings}
    save_cache(cache)

    msg = "Student photos updated successfully." if student else "Enrollment successful."
    return {"ok": True, "message": msg}


# ==============================
# Delete Student
# ==============================
@router.delete("/student/delete/{student_id}")
def delete_student(
    student_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_dirs()
    sid = _normalize_student_code(student_id)

    if not sid:
        return {"ok": False, "message": "Student ID is required."}

    # Get scoped student info BEFORE deleting for folder cleanup.
    student_info = _find_scoped_student(db=db, current_user=current_user, student_code=sid)
    if not student_info:
        return {"ok": False, "message": "Student not found in your scope."}
    internal_sid = student_info.id

    # ✅ SQLite trial: Attendance uses student_id
    db.query(Attendance).filter(Attendance.student_id == internal_sid).delete()
    db.query(Student).filter(Student.id == internal_sid).delete()
    db.commit()

    # Cache delete
    cache = load_cache()
    students = cache.get("students", {})
    for cache_key in {internal_sid, sid}:
        if cache_key in students:
            students.pop(cache_key, None)
    cache["students"] = students
    save_cache(cache)

    # Photos folder delete - use actual school_name from student record
    if student_info:
        folder = get_student_folder_path(student_info.school_name or "MainSchool", 
                                          student_info.class_name, 
                                          student_info.section, _display_student_id(student_info))
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass

    return {"ok": True, "message": f"Student {sid} deleted successfully."}


# ==============================
# Students List
# ==============================
@router.get("/students")
def list_students(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all students list (filtered by school for non-super-admins)"""
    query = _apply_student_scope(db.query(Student), current_user)
    students = query.all()

    result = []
    for s in students:
        result.append({
            "id": _display_student_id(s),
            "name": s.name,
            "class_name": s.class_name,
            "section": s.section,
            "roll": s.roll,
            "school_name": s.school_name
        })

    return {"ok": True, "students": result}


@router.get("/filters/distinct")
def get_distinct_filters(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get distinct schools, classes, and sections for filter dropdowns"""
    query = _apply_student_scope(db.query(Student), current_user)

    schools = [r[0] for r in query.with_entities(Student.school_name).distinct().order_by(Student.school_name).all() if r[0]]
    classes = [r[0] for r in query.with_entities(Student.class_name).distinct().order_by(Student.class_name).all() if r[0]]
    sections = [r[0] for r in query.with_entities(Student.section).distinct().order_by(Student.section).all() if r[0]]

    return {
        "ok": True,
        "schools": schools,
        "classes": classes,
        "sections": sections
    }


# ==============================
# Attendance Mark
# ==============================
@router.post("/attendance/mark")
async def mark_attendance(
    file: UploadFile = File(...),
    mode: str = Form("in"),
    student_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_dirs()

    cache = load_cache()
    all_cached_students = cache.get("students", {})
    scoped_students = _apply_student_scope(db.query(Student), current_user).all()
    canonical_by_key: Dict[str, str] = {}
    for s in scoped_students:
        canonical_by_key[str(s.id).strip()] = s.id
        display_sid = _display_student_id(s)
        if display_sid:
            canonical_by_key[display_sid] = s.id
    students = {}
    for cache_sid, data in all_cached_students.items():
        key = canonical_by_key.get(str(cache_sid).strip())
        if key and key not in students:
            students[key] = data

    if not students:
        return {"ok": False, "message": "No students found in your assigned scope."}

    # Read image as OpenCV BGR for InsightFace and MiniFASNet
    contents = await file.read()
    img = cv2.imdecode(np.frombuffer(contents, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "message": "Invalid image file."}

    # Liveness first, then identify
    best_sid, _, best_distance, match_meta = identify_from_image_array(img, students)

    if match_meta.get("spoof_rejected"):
        return {
            "ok": False,
            "message": match_meta.get("message", "Spoofing detected"),
            "antispoofing": match_meta.get("antispoofing"),
        }

    if best_sid is None:
        return {
            "ok": False,
            "message": match_meta.get("message") or "No match found",
            "antispoofing": match_meta.get("antispoofing"),
        }

    if best_distance is None or best_distance > MATCH_THRESHOLD:
        return {
            "ok": False,
            "message": "No match found",
            "match_distance": round(float(best_distance or 999.0), 4),
            "antispoofing": match_meta.get("antispoofing"),
        }

    sid = str(best_sid).strip()
    requested_student = _find_scoped_student(
        db=db,
        current_user=current_user,
        student_code=(student_id or "").strip(),
    ) if (student_id or "").strip() else None
    if (student_id or "").strip() and not requested_student:
        return {"ok": False, "message": "Selected student not found in your scope."}
    if requested_student and requested_student.id != sid:
        return {"ok": False, "message": "Face does not match selected student."}

    # Must exist in roster DB
    student = db.query(Student).filter(Student.id == sid).first()
    if not student:
        return {"ok": False, "message": "This person is not in classroom"}
    if not _student_visible_to_user(student, current_user):
        return {"ok": False, "message": "Matched student is outside your assigned school/class"}

    now = datetime.now()
    today = now.date()

    # ✅ SQLite trial: keep one record per student per day
    record = (
        db.query(Attendance)
        .filter(Attendance.student_id == sid)
        .filter(Attendance.date == today)
        .order_by(Attendance.id.desc())
        .first()
    )

    mode = (mode or "in").strip().lower()
    if mode not in ("in", "out"):
        return {"ok": False, "message": "Invalid mode. Use 'in' or 'out'."}

    # IN
    if mode == "in":
        if record and record.in_time is not None:
            return {
                "ok": True,
                "message": "IN already marked",
                "student_id": _display_student_id(student),
                "name": student.name,
                "in_time": record.in_time.strftime("%Y-%m-%d %H:%M:%S"),
                "match_distance": round(float(best_distance), 4),
                "antispoofing": match_meta.get("antispoofing"),
            }

        new_record = Attendance(
            student_id=sid,
            date=today,
            status="P",
            biometric_method="face",
            in_time=now,         # ✅ DateTime for SQLite trial
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "ok": True,
            "message": "In time marked",
            "student_id": _display_student_id(student),
            "name": student.name,
            "in_time": new_record.in_time.strftime("%Y-%m-%d %H:%M:%S"),
            "match_distance": round(float(best_distance), 4),
            "antispoofing": match_meta.get("antispoofing"),
        }

    # OUT
    if not record or record.in_time is None:
        return {"ok": False, "message": "IN not marked yet. Please mark IN first."}

    if record.out_time is not None:
        return {
            "ok": True,
            "message": "Out already marked",
            "student_id": _display_student_id(student),
            "name": student.name,
            "out_time": record.out_time.strftime("%Y-%m-%d %H:%M:%S"),
            "match_distance": round(float(best_distance), 4),
            "antispoofing": match_meta.get("antispoofing"),
        }

    record.out_time = now      # ✅ DateTime for SQLite trial
    record.updated_at = now
    db.commit()

    return {
        "ok": True,
        "message": "Out time marked",
        "student_id": _display_student_id(student),
        "name": student.name,
        "out_time": record.out_time.strftime("%Y-%m-%d %H:%M:%S"),
        "match_distance": round(float(best_distance), 4),
        "antispoofing": match_meta.get("antispoofing"),
    }


@router.post("/attendance/manual")
def manual_attendance(
    student_id: str = Form(...),
    status: str = Form("P"),
    date: str = Form(""),
    remark: str = Form("Manual attendance"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sid = _normalize_student_code(student_id)
    status = (status or "P").strip().upper()
    if status not in {"P", "A", "L"}:
        return {"ok": False, "message": "Status must be P, A, or L."}
    student = _find_scoped_student(db=db, current_user=current_user, student_code=sid)
    if not student:
        return {"ok": False, "message": "Student not found."}
    internal_sid = student.id
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
    except ValueError:
        return {"ok": False, "message": "Invalid date. Use YYYY-MM-DD."}
    now = datetime.now()
    record = (
        db.query(Attendance)
        .filter(Attendance.student_id == internal_sid, Attendance.date == target_date)
        .order_by(Attendance.id.desc())
        .first()
    )
    if record:
        record.status = status
        record.remark = remark or "Manual attendance"
        record.updated_at = now
        record.in_time = now if status in {"P", "L"} and not record.in_time else record.in_time
        if status == "A":
            record.in_time = None
            record.out_time = None
    else:
        record = Attendance(
            student_id=internal_sid,
            date=target_date,
            status=status,
            biometric_method=None,
            remark=remark or "Manual attendance",
            in_time=now if status in {"P", "L"} else None,
        )
        db.add(record)
    db.commit()
    return {"ok": True, "message": f"{student.name} marked {status}", "student_id": _display_student_id(student), "status": status}


@router.post("/attendance/bulk")
def bulk_attendance(
    records: List[dict] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime
    now = datetime.now()
    updated_count = 0
    for data in records:
        sid = _normalize_student_code(data.get("student_id", ""))
        status = str(data.get("status", "P")).strip().upper()
        date_str = data.get("date", "")
        if status not in {"P", "A", "L"}:
            continue
        student = _find_scoped_student(db=db, current_user=current_user, student_code=sid)
        if not student:
            continue
        internal_sid = student.id
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else now.date()
        except ValueError:
            target_date = now.date()
            
        record = (
            db.query(Attendance)
            .filter(Attendance.student_id == internal_sid, Attendance.date == target_date)
            .order_by(Attendance.id.desc())
            .first()
        )
        if record:
            record.status = status
            record.remark = "Manual bulk attendance"
            record.updated_at = now
            record.in_time = now if status in {"P", "L"} and not record.in_time else record.in_time
            if status == "A":
                record.in_time = None
                record.out_time = None
        else:
            record = Attendance(
                student_id=internal_sid,
                date=target_date,
                status=status,
                biometric_method=None,
                remark="Manual bulk attendance",
                in_time=now if status in {"P", "L"} else None,
            )
            db.add(record)
        updated_count += 1
    db.commit()
    return {"ok": True, "message": f"Successfully updated {updated_count} records.", "updated_count": updated_count}



@router.get("/attendance/by-date")
def attendance_by_date(
    date: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
    except ValueError:
        target_date = datetime.now().date()
    students = _apply_student_scope(db.query(Student), current_user).all()
    student_map = {s.id: s for s in students}
    if not student_map:
        return {"ok": True, "records": []}
    rows = db.query(Attendance).filter(Attendance.date == target_date, Attendance.student_id.in_(student_map.keys())).all()
    records = []
    for row in rows:
        s = student_map.get(row.student_id)
        records.append({
            "student_id": _display_student_id(s) if s else row.student_id,
            "name": s.name if s else "",
            "class_name": s.class_name if s else "",
            "section": s.section if s else "",
            "roll": s.roll if s else "",
            "status": row.status,
            "date": str(row.date),
            "in_time": row.in_time.strftime("%H:%M:%S") if row.in_time else "",
            "out_time": row.out_time.strftime("%H:%M:%S") if row.out_time else "",
        })
    return {"ok": True, "records": records}


@router.get("/attendance/today")
def attendance_today(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_date = datetime.now().date()
    students = _apply_student_scope(db.query(Student), current_user).all()
    student_map = {s.id: s for s in students}
    if not student_map:
        return {"ok": True, "records": []}

    rows = db.query(Attendance).filter(
        Attendance.date == target_date,
        Attendance.student_id.in_(student_map.keys()),
    ).all()
    records = []
    for row in rows:
        s = student_map.get(row.student_id)
        records.append({
            "student_id": _display_student_id(s) if s else row.student_id,
            "name": s.name if s else "",
            "class_name": s.class_name if s else "",
            "section": s.section if s else "",
            "roll": s.roll if s else "",
            "status": row.status,
            "date": str(row.date),
            "in_time": row.in_time.strftime("%H:%M:%S") if row.in_time else "",
            "out_time": row.out_time.strftime("%H:%M:%S") if row.out_time else "",
        })
    return {"ok": True, "records": records}


# ==============================
# Export Excel (Today)
# ==============================
@router.get("/attendance/export/today")
def export_today_attendance_excel_route(
    school_name: str = None,
    class_name: str = None,
    section: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export today's attendance as Excel file for client download"""
    # Non-super-admins can only export their own school's data
    if user_role(current_user) != "SUPER_ADMIN":
        school_name = user_school(current_user) or school_name
        
    if user_role(current_user) == "TEACHER":
        class_name = getattr(current_user, "class_assigned", "") or class_name
        section = getattr(current_user, "section_assigned", "") or section

    return export_today_attendance_excel(
        db,
        school_name=school_name,
        class_name=class_name,
        section=section
    )


# ==============================
# Export Excel (Custom Range)
# ==============================
@router.get("/attendance/export/excel")
def export_attendance_excel_route(
    start_date: str = None,
    end_date: str = None,
    school_name: str = None,
    class_name: str = None,
    section: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export attendance as Excel file with custom filters"""
    from datetime import datetime
    
    # Parse dates if provided
    start_dt = None
    end_dt = None
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    # Non-super-admins can only export their own school's data
    if user_role(current_user) != "SUPER_ADMIN":
        school_name = user_school(current_user) or school_name

    if user_role(current_user) == "TEACHER":
        class_name = getattr(current_user, "class_assigned", "") or class_name
        section = getattr(current_user, "section_assigned", "") or section

    return export_attendance_excel(
        db,
        start_date=start_dt,
        end_date=end_dt,
        school_name=school_name,
        class_name=class_name,
        section=section
    )


# ==============================
# Export Summary Excel
# ==============================
@router.get("/attendance/export/summary")
def export_summary_excel_route(
    start_date: str = None,
    end_date: str = None,
    school_name: str = None,
    class_name: str = None,
    section: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export attendance summary as Excel file"""
    from datetime import datetime
    
    # Parse dates if provided
    start_dt = None
    end_dt = None
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    # Non-super-admins can only export their own school's data
    if user_role(current_user) != "SUPER_ADMIN":
        school_name = user_school(current_user) or school_name

    if user_role(current_user) == "TEACHER":
        class_name = getattr(current_user, "class_assigned", "") or class_name
        section = getattr(current_user, "section_assigned", "") or section

    return generate_summary_excel(
        db,
        start_date=start_dt,
        end_date=end_dt,
        school_name=school_name,
        class_name=class_name,
        section=section
    )


# ==============================
# Analytics Dashboard APIs
# ==============================
@router.get("/analytics/summary")
def analytics_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Overall attendance summary for dashboard"""
    from datetime import date, timedelta

    today = date.today()
    week_ago = today - timedelta(days=6)
    month_ago = today - timedelta(days=29)

    # Base query filtered by school for non-super-admins
    base_student_query = _apply_student_scope(db.query(Student), current_user)
    scoped_students = base_student_query.all()
    scoped_ids = [s.id for s in scoped_students]
    base_attendance_query = db.query(Attendance)
    if scoped_ids:
        base_attendance_query = base_attendance_query.filter(Attendance.student_id.in_(scoped_ids))
    else:
        base_attendance_query = base_attendance_query.filter(Attendance.student_id == "__none__")

    total_students = len(scoped_students)
    present_today = base_attendance_query.filter(Attendance.date == today, Attendance.status == 'P').count()
    present_this_week = base_attendance_query.filter(Attendance.date >= week_ago, Attendance.status == 'P').count()
    present_this_month = base_attendance_query.filter(Attendance.date >= month_ago, Attendance.status == 'P').count()

    # Working days approximation (Mon-Fri)
    def count_working_days(start, end):
        count = 0
        d = start
        while d <= end:
            if d.weekday() < 5:
                count += 1
            d += timedelta(days=1)
        return max(count, 1)

    week_working = count_working_days(week_ago, today)
    month_working = count_working_days(month_ago, today)

    return {
        "ok": True,
        "total_students": total_students,
        "present_today": present_today,
        "weekly_avg": round(present_this_week / max(total_students * week_working, 1) * 100, 1),
        "monthly_avg": round(present_this_month / max(total_students * month_working, 1) * 100, 1),
    }


@router.get("/analytics/class-wise")
def analytics_class_wise(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Class-wise attendance percentage for current month"""
    from datetime import date, timedelta

    today = date.today()
    month_start = today.replace(day=1)

    # Filter by school for non-super-admins
    student_query = _apply_student_scope(db.query(Student), current_user)
    scoped_ids = [s.id for s in student_query.all()]
    attend_query = db.query(Attendance).join(Student)
    if scoped_ids:
        attend_query = attend_query.filter(Attendance.student_id.in_(scoped_ids))
    else:
        attend_query = attend_query.filter(Attendance.student_id == "__none__")

    # Get all classes
    classes = [r[0] for r in student_query.with_entities(Student.class_name).distinct().all() if r[0]]

    # Count working days this month so far
    working_days = 0
    d = month_start
    while d <= today:
        if d.weekday() < 5:
            working_days += 1
        d += timedelta(days=1)
    working_days = max(working_days, 1)

    result = []
    for cls in classes:
        total = student_query.filter(Student.class_name == cls).count()
        present = attend_query.filter(
            Student.class_name == cls,
            Attendance.date >= month_start,
            Attendance.status == 'P'
        ).count()
        pct = round(present / max(total * working_days, 1) * 100, 1)
        result.append({"class": cls, "total_students": total, "present_count": present, "percentage": pct})

    return {"ok": True, "data": result}


@router.get("/analytics/class-dashboard")
def analytics_class_dashboard(
    date: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
    except ValueError:
        target_date = datetime.now().date()
    students = _apply_student_scope(db.query(Student), current_user).order_by(Student.class_name, Student.section, Student.roll, Student.name).all()
    ids = [s.id for s in students]
    rows = db.query(Attendance).filter(Attendance.date == target_date, Attendance.student_id.in_(ids)).all() if ids else []
    row_map = {r.student_id: r for r in rows}
    groups = {}
    for s in students:
        key = (s.school_name or "", s.class_name or "Unassigned", s.section or "Unassigned")
        g = groups.setdefault(key, {
            "school_name": key[0],
            "class_name": key[1],
            "section": key[2],
            "total": 0,
            "present": 0,
            "late": 0,
            "absent": 0,
            "students": [],
        })
        r = row_map.get(s.id)
        status = r.status if r else "A"
        if status == "P":
            g["present"] += 1
            label = "Present"
        elif status == "L":
            g["late"] += 1
            label = "Late"
        else:
            g["absent"] += 1
            label = "Absent"
        g["total"] += 1
        g["students"].append({"id": _display_student_id(s), "name": s.name, "roll": s.roll, "status": label})
    out = []
    for g in groups.values():
        g["attendance_rate"] = round(((g["present"] + g["late"]) / max(g["total"], 1)) * 100, 1)
        out.append(g)
    return {"ok": True, "date": str(target_date), "classes": out}


@router.get("/analytics/monthly")
def analytics_monthly(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Daily attendance trend for current month"""
    from datetime import date, timedelta

    today = date.today()
    month_start = today.replace(day=1)

    scoped_ids = [s.id for s in _apply_student_scope(db.query(Student), current_user).all()]
    attend_query = db.query(Attendance)
    if scoped_ids:
        attend_query = attend_query.filter(Attendance.student_id.in_(scoped_ids))
    else:
        attend_query = attend_query.filter(Attendance.student_id == "__none__")

    # Get daily present counts
    daily = (
        attend_query
        .filter(Attendance.date >= month_start, Attendance.status == 'P')
        .with_entities(Attendance.date, func.count(Attendance.id))
        .group_by(Attendance.date)
        .order_by(Attendance.date)
        .all()
    )

    labels = []
    values = []
    d = month_start
    while d <= today:
        labels.append(d.strftime('%d %b'))
        # Find count for this date
        count = next((c for date_obj, c in daily if date_obj == d), 0)
        values.append(count)
        d += timedelta(days=1)

    return {"ok": True, "labels": labels, "values": values}


@router.get("/analytics/defaulters")
def analytics_defaulters(
    threshold: int = 75,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Students with attendance below threshold % this month"""
    from datetime import date, timedelta

    today = date.today()
    month_start = today.replace(day=1)

    # Working days count
    working_days = 0
    d = month_start
    while d <= today:
        if d.weekday() < 5:
            working_days += 1
        d += timedelta(days=1)
    working_days = max(working_days, 1)

    student_query = _apply_student_scope(db.query(Student), current_user)

    students = student_query.all()
    defaulters = []

    for s in students:
        present = db.query(Attendance).filter(
            Attendance.student_id == s.id,
            Attendance.date >= month_start,
            Attendance.status == 'P'
        ).count()
        pct = round(present / working_days * 100, 1)
        if pct < threshold:
            defaulters.append({
                "id": _display_student_id(s),
                "name": s.name,
                "class": s.class_name,
                "section": s.section,
                "present_days": present,
                "total_days": working_days,
                "percentage": pct
            })

    defaulters.sort(key=lambda x: x["percentage"])
    return {"ok": True, "defaulters": defaulters, "threshold": threshold}
