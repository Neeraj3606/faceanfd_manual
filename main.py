"""
Main entrypoint for Face Attendance Service

Responsibilities:
+ Create FastAPI app
+ Register routes
+ Initialize database tables automatically
+ Start server
"""

import os
import socket
import subprocess
import sys


def _bootstrap_project_python() -> None:
    """Re-run with the local virtualenv so `python main.py` uses project deps."""
    if os.getenv("FACE_ATTENDANCE_SKIP_VENV_BOOTSTRAP") == "1":
        return

    project_root = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(project_root, ".venv311", "bin", "python")

    if not os.path.exists(venv_python):
        return

    current_python = os.path.realpath(sys.executable)
    target_python = os.path.realpath(venv_python)
    if current_python == target_python:
        return

    env = os.environ.copy()
    env["FACE_ATTENDANCE_SKIP_VENV_BOOTSTRAP"] = "1"
    raise SystemExit(subprocess.call([venv_python, __file__], env=env))


_bootstrap_project_python()

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import uvicorn

from app.routes import router
from app.auth_routes import router as auth_router
from app.config import HOST, PORT, PROJECT_ROOT
from app.storage import ensure_dirs

# ✅ Database
from app.db import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _ensure_super_admin()
    yield


def _ensure_super_admin():
    from app.db import SessionLocal
    from app.models import User
    from app.auth import get_password_hash
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.is_super_admin == True).first():
            db.add(User(
                username='superadmin@gmail.com',
                email='superadmin@gmail.com',
                hashed_password=get_password_hash('superadmin123'),
                full_name='Super Administrator',
                role='SUPER_ADMIN',
                school_name='',
                is_active=True,
                is_admin=True,
                is_super_admin=True,
            ))
            db.commit()
    finally:
        db.close()


def _run_migrations():
    from app.db import engine as _engine
    from sqlalchemy import text
    import hashlib
    migrations = [
        ("users", "is_super_admin",   "INTEGER NOT NULL DEFAULT 0"),
        ("users", "updated_at",       "DATETIME"),
        ("users", "role",             "VARCHAR(30) NOT NULL DEFAULT 'ADMIN'"),
        ("users", "school_name",      "VARCHAR(100) DEFAULT ''"),
        ("users", "class_assigned",   "VARCHAR(100) DEFAULT ''"),
        ("users", "section_assigned", "VARCHAR(50) DEFAULT ''"),
        ("students", "school_name",   "VARCHAR DEFAULT ''"),
        ("students", "student_code",  "VARCHAR(50) DEFAULT ''"),
    ]
    with _engine.connect() as conn:
        for table, col, defn in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {defn}"))
                conn.commit()
            except Exception:
                pass

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS face_encodings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id VARCHAR(50) NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                student_name VARCHAR(255) NOT NULL DEFAULT '',
                encoding_blob BLOB NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME
            )
        """))
        conn.commit()

        conn.execute(text("UPDATE users SET role='SUPER_ADMIN' WHERE is_super_admin=1"))
        conn.execute(text("UPDATE users SET role='ADMIN' WHERE is_super_admin=0 AND is_admin=1"))
        conn.execute(text("UPDATE users SET role='TEACHER' WHERE is_super_admin=0 AND is_admin=0"))
        conn.execute(text("UPDATE users SET school_name=COALESCE(NULLIF(school_name,''), full_name, '') WHERE role='ADMIN'"))
        conn.execute(text("UPDATE users SET email='superadmin@gmail.com' WHERE is_super_admin=1 AND COALESCE(email,'')=''"))
        conn.execute(text("UPDATE students SET student_code=id WHERE COALESCE(student_code,'')=''"))
        conn.commit()

        rows = conn.execute(text("SELECT id, COALESCE(student_code,''), COALESCE(school_name,'') FROM students")).fetchall()
        for old_id, student_code, school_name in rows:
            code = (student_code or old_id or "").strip()
            school = (school_name or "").strip().lower()
            if not code:
                continue
            scoped_id = "sid_" + hashlib.sha1(f"{school}|{code.lower()}".encode()).hexdigest()
            if old_id == scoped_id:
                continue
            if conn.execute(text("SELECT 1 FROM students WHERE id=:id LIMIT 1"), {"id": scoped_id}).fetchone():
                continue
            conn.execute(text("UPDATE attendance SET student_id=:new_id WHERE student_id=:old_id"), {"new_id": scoped_id, "old_id": old_id})
            conn.execute(text("UPDATE students SET id=:new_id WHERE id=:old_id"), {"new_id": scoped_id, "old_id": old_id})
        conn.commit()


app = FastAPI(
    title="Face Attendance Service",
    version="1.0.0",
    description="Offline Face Recognition Attendance System",
    lifespan=lifespan,
)

from fastapi import Request
from fastapi.responses import JSONResponse
import traceback
import logging

logger = logging.getLogger("face_attendance")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log full traceback server-side only — NEVER expose to client
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

# ✅ CORS — read from env variable ALLOWED_ORIGINS (comma-separated list).
# Default: allow localhost only. Set ALLOWED_ORIGINS=* only for development.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").strip()
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ✅ Static files (Frontend)
frontend_path = os.path.join(PROJECT_ROOT, "Frontend")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

# ✅ Root redirect to login page
@app.get("/")
def root():
    return RedirectResponse(url="/static/login.html")

# ✅ Routes
app.include_router(auth_router)
app.include_router(router)


def _is_port_available(host: str, port: int) -> bool:
    """Return True when the host/port can be bound by a new server."""
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((probe_host, port))
        except OSError:
            return False
    return True


def _resolve_server_port(host: str, preferred_port: int, search_limit: int = 20) -> int:
    """Use the preferred port when available, otherwise fall forward to the next free port."""
    if _is_port_available(host, preferred_port):
        return preferred_port

    for port in range(preferred_port + 1, preferred_port + search_limit + 1):
        if _is_port_available(host, port):
            print(
                f"⚠️ Port {preferred_port} is already in use. "
                f"Starting Face Attendance on port {port} instead."
            )
            return port

    raise RuntimeError(
        f"No free port found between {preferred_port} and {preferred_port + search_limit}."
    )


if __name__ == "__main__":
    resolved_port = _resolve_server_port(HOST, PORT)
    browser_host = "127.0.0.1" if HOST == "0.0.0.0" else HOST
    print(f"📡 Face Attendance starting on http://{browser_host}:{resolved_port}")
    uvicorn.run(
        "main:app",
        host=HOST,
        port=resolved_port,
        reload=False,  # client delivery: stable
    )
