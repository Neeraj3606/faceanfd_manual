"""
AI Insights Module — Gemini-powered attendance analysis bot.

Provides:
  - build_teacher_context()  → attendance summary for a teacher's class
  - build_admin_context()    → school-wide attendance summary for admin
  - generate_insights()      → auto-generated narrative bullet points
  - answer_question()        → free-form Q&A grounded in attendance data
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Attendance, Student, User
from app.auth import user_role, user_school

# ─────────────────────────────────────────────────────────────────
# AI Client Initialisation (Gemini)
# ─────────────────────────────────────────────────────────────────

def gemini_available() -> bool:
    """Return True when a valid Gemini API key is configured."""
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


# Backward-compatible alias so routes.py doesn't need changes
grok_available = gemini_available


def ai_model_name() -> str:
    """Return the name of the active AI model."""
    return f"Gemini ({os.getenv('GEMINI_MODEL', 'gemini-1.5-flash').strip()})"


# ─────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────

def _working_days(start: date, end: date) -> int:
    count = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return max(count, 1)


def _student_monthly_pct(db: Session, student_id: str, month_start: date, today: date, working_days: int) -> float:
    present = db.query(Attendance).filter(
        Attendance.student_id == student_id,
        Attendance.date >= month_start,
        Attendance.date <= today,
        Attendance.status == "P",
    ).count()
    return round(present / working_days * 100, 1)


# ─────────────────────────────────────────────────────────────────
# Context builders
# ─────────────────────────────────────────────────────────────────

def build_teacher_context(db: Session, current_user: User) -> Dict[str, Any]:
    """Build attendance context for a teacher's assigned class."""
    from app.routes import _apply_student_scope

    today = date.today()
    month_start = today.replace(day=1)
    week_ago = today - timedelta(days=6)
    wd_month = _working_days(month_start, today)
    wd_week = _working_days(week_ago, today)

    students = _apply_student_scope(db.query(Student), current_user).order_by(Student.name).all()
    ids = [s.id for s in students]

    if not ids:
        return {
            "role": "TEACHER",
            "class": getattr(current_user, "class_assigned", "") or "Unknown",
            "section": getattr(current_user, "section_assigned", "") or "Unknown",
            "school": user_school(current_user) or "Unknown",
            "today": str(today),
            "total_students": 0,
            "message": "No students assigned to this teacher.",
            "students": [],
        }

    # Today's attendance
    today_rows = db.query(Attendance).filter(
        Attendance.date == today,
        Attendance.student_id.in_(ids),
    ).all()
    today_map = {r.student_id: r for r in today_rows}

    present_today = sum(1 for r in today_rows if r.status == "P")
    late_today = sum(1 for r in today_rows if r.status == "L")
    absent_today = len(ids) - present_today - late_today

    # Per-student monthly stats
    student_details: List[Dict] = []
    defaulters: List[Dict] = []

    for s in students:
        pct = _student_monthly_pct(db, s.id, month_start, today, wd_month)
        t_row = today_map.get(s.id)
        status_today = t_row.status if t_row else "A"
        in_time = t_row.in_time.strftime("%H:%M") if t_row and t_row.in_time else None

        entry = {
            "id": s.student_code or s.id,
            "name": s.name,
            "roll": s.roll,
            "status_today": status_today,
            "in_time": in_time,
            "monthly_pct": pct,
        }
        student_details.append(entry)
        if pct < 75:
            defaulters.append({"name": s.name, "pct": pct})

    # Week trend (daily present counts)
    week_trend: List[Dict] = []
    d = week_ago
    while d <= today:
        cnt = db.query(Attendance).filter(
            Attendance.date == d,
            Attendance.student_id.in_(ids),
            Attendance.status == "P",
        ).count()
        week_trend.append({"date": str(d), "present": cnt, "total": len(ids)})
        d += timedelta(days=1)

    return {
        "role": "TEACHER",
        "teacher_name": current_user.full_name or current_user.username,
        "class": getattr(current_user, "class_assigned", "") or "Unknown",
        "section": getattr(current_user, "section_assigned", "") or "Unknown",
        "school": user_school(current_user) or "Unknown",
        "today": str(today),
        "total_students": len(ids),
        "present_today": present_today,
        "late_today": late_today,
        "absent_today": absent_today,
        "attendance_pct_today": round(present_today / max(len(ids), 1) * 100, 1),
        "working_days_this_month": wd_month,
        "working_days_this_week": wd_week,
        "defaulters_below_75pct": defaulters,
        "week_trend": week_trend,
        "students": student_details,
    }


def build_admin_context(db: Session, current_user: User) -> Dict[str, Any]:
    """Build school-wide attendance context for an admin."""
    from app.routes import _apply_student_scope

    today = date.today()
    month_start = today.replace(day=1)
    week_ago = today - timedelta(days=6)
    wd_month = _working_days(month_start, today)

    students = _apply_student_scope(db.query(Student), current_user).all()
    ids = [s.id for s in students]

    if not ids:
        return {
            "role": "ADMIN",
            "school": user_school(current_user) or "Unknown",
            "today": str(today),
            "total_students": 0,
            "message": "No students enrolled.",
            "classes": [],
        }

    today_rows = db.query(Attendance).filter(
        Attendance.date == today,
        Attendance.student_id.in_(ids),
    ).all()
    today_map = {r.student_id: r for r in today_rows}

    present_today = sum(1 for r in today_rows if r.status == "P")
    absent_today = len(ids) - present_today

    # Per-class breakdown
    class_map: Dict[str, Dict] = {}
    for s in students:
        key = f"{s.class_name or 'Unknown'}-{s.section or 'Unknown'}"
        if key not in class_map:
            class_map[key] = {
                "class": s.class_name or "Unknown",
                "section": s.section or "Unknown",
                "total": 0,
                "present_today": 0,
                "monthly_present": 0,
            }
        class_map[key]["total"] += 1
        t_row = today_map.get(s.id)
        if t_row and t_row.status == "P":
            class_map[key]["present_today"] += 1

        # Monthly count
        monthly_p = db.query(Attendance).filter(
            Attendance.student_id == s.id,
            Attendance.date >= month_start,
            Attendance.date <= today,
            Attendance.status == "P",
        ).count()
        class_map[key]["monthly_present"] += monthly_p

    # Compute percentages
    classes_list = []
    for k, v in class_map.items():
        v["today_pct"] = round(v["present_today"] / max(v["total"], 1) * 100, 1)
        v["monthly_pct"] = round(v["monthly_present"] / max(v["total"] * wd_month, 1) * 100, 1)
        classes_list.append(v)

    # Sort by today_pct ascending (worst first)
    classes_list.sort(key=lambda x: x["today_pct"])

    # Defaulters (monthly < 75%)
    defaulters: List[Dict] = []
    for s in students:
        pct = _student_monthly_pct(db, s.id, month_start, today, wd_month)
        if pct < 75:
            defaulters.append({
                "name": s.name,
                "class": s.class_name,
                "section": s.section,
                "pct": pct,
            })
    defaulters.sort(key=lambda x: x["pct"])

    # Week trend
    week_trend: List[Dict] = []
    d = week_ago
    while d <= today:
        cnt = db.query(Attendance).filter(
            Attendance.date == d,
            Attendance.student_id.in_(ids),
            Attendance.status == "P",
        ).count()
        week_trend.append({"date": str(d), "present": cnt, "total": len(ids)})
        d += timedelta(days=1)

    return {
        "role": "ADMIN",
        "school": user_school(current_user) or "Unknown",
        "today": str(today),
        "total_students": len(ids),
        "present_today": present_today,
        "absent_today": absent_today,
        "attendance_pct_today": round(present_today / max(len(ids), 1) * 100, 1),
        "working_days_this_month": wd_month,
        "classes": classes_list,
        "defaulters_below_75pct": defaulters[:20],  # top 20 worst
        "week_trend": week_trend,
    }


# ─────────────────────────────────────────────────────────────────
# Prompt builders
# ─────────────────────────────────────────────────────────────────

_TEACHER_SYSTEM = """You are an AI attendance assistant for a school teacher. 
Your job is to analyze attendance data and provide clear, actionable insights.
- Be concise and specific — use student names and numbers
- Format your response as 4-6 bullet points using • 
- Highlight students with low attendance (below 75%)
- Note positive trends too
- Keep language friendly and professional
- Do NOT make up data — only use what is provided
- Respond in plain text, no markdown headers"""

_ADMIN_SYSTEM = """You are an AI attendance analytics assistant for a school administrator.
Your job is to analyze school-wide attendance data and provide strategic insights.
- Be concise and data-driven — mention class names and percentages
- Format your response as 4-6 bullet points using •
- Highlight the best and worst performing classes
- Flag critical issues (classes below 70%)
- Suggest actionable steps where relevant
- Do NOT make up data — only use what is provided
- Respond in plain text, no markdown headers"""


def _context_to_text(ctx: Dict[str, Any]) -> str:
    """Convert context dict to a readable text block for the prompt."""
    import json
    return json.dumps(ctx, indent=2, default=str)


def _call_gemini(system_prompt: str, user_prompt: str) -> str:
    """Call the Google Gemini API and return the response text."""
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return "⚠️ AI Insights is not configured. Please add your GEMINI_API_KEY to the .env file and restart the server."

    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_key)

        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
            ),
        )
        return response.text.strip()

    except Exception as e:
        return f"⚠️ Gemini API error: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def generate_insights(db: Session, current_user: User) -> Dict[str, Any]:
    """Generate automatic narrative insights based on role."""
    role = user_role(current_user)

    if role == "TEACHER":
        ctx = build_teacher_context(db, current_user)
        system = _TEACHER_SYSTEM
        user_msg = (
            f"Here is today's attendance data for my class "
            f"{ctx.get('class', '')}-{ctx.get('section', '')} at {ctx.get('school', '')}:\n"
            f"{_context_to_text(ctx)}\n\n"
            f"Please give me smart insights about today's attendance and this month's trends."
        )
    elif role in ("ADMIN", "SUPER_ADMIN"):
        ctx = build_admin_context(db, current_user)
        system = _ADMIN_SYSTEM
        user_msg = (
            f"Here is the school-wide attendance data for {ctx.get('school', 'the school')}:\n"
            f"{_context_to_text(ctx)}\n\n"
            f"Please give me a strategic overview of attendance performance and key concerns."
        )
    else:
        return {"ok": False, "message": "Unsupported role for AI insights."}

    insight_text = _call_gemini(system, user_msg)

    return {
        "ok": True,
        "role": role,
        "insight": insight_text,
        "context_summary": {
            "total_students": ctx.get("total_students", 0),
            "present_today": ctx.get("present_today", 0),
            "attendance_pct_today": ctx.get("attendance_pct_today", 0),
            "defaulters_count": len(ctx.get("defaulters_below_75pct", [])),
        },
    }


def answer_question(db: Session, current_user: User, question: str) -> Dict[str, Any]:
    """Answer a free-form question about attendance data."""
    role = user_role(current_user)
    question = (question or "").strip()

    if not question:
        return {"ok": False, "message": "Please provide a question."}

    if role == "TEACHER":
        ctx = build_teacher_context(db, current_user)
        system = _TEACHER_SYSTEM
        user_msg = (
            f"Attendance data for class {ctx.get('class', '')}-{ctx.get('section', '')}:\n"
            f"{_context_to_text(ctx)}\n\n"
            f"Teacher's question: {question}\n\n"
            f"Please answer based only on the data above."
        )
    elif role in ("ADMIN", "SUPER_ADMIN"):
        ctx = build_admin_context(db, current_user)
        system = _ADMIN_SYSTEM
        user_msg = (
            f"School attendance data for {ctx.get('school', 'the school')}:\n"
            f"{_context_to_text(ctx)}\n\n"
            f"Admin's question: {question}\n\n"
            f"Please answer based only on the data above."
        )
    else:
        return {"ok": False, "message": "Unsupported role."}

    answer_text = _call_gemini(system, user_msg)

    return {
        "ok": True,
        "question": question,
        "answer": answer_text,
    }
