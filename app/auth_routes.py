"""
Authentication routes for login/logout and user management
"""

import os
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_token,
    get_current_user,
    get_admin_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    user_role,
    user_school,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


# =========================
# Pydantic Models
# =========================
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_admin: bool = False
    role: Optional[str] = None
    school_name: Optional[str] = None
    class_assigned: Optional[str] = None
    section_assigned: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    school_name: Optional[str] = None
    class_assigned: Optional[str] = None
    section_assigned: Optional[str] = None
    is_active: bool
    is_admin: bool
    is_super_admin: bool = False

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    full_name: Optional[str] = None
    class_assigned: Optional[str] = None
    section_assigned: Optional[str] = None

    class Config:
        from_attributes = True


# =========================
# Login
# =========================
@router.post("/login", response_model=Token)
def login(
    username: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Login with username and password to get JWT token"""
    login_id = (username or email or "").strip()
    if not login_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username or email is required",
        )

    # Find user
    user = db.query(User).filter(
        or_(User.username == login_id, User.email == login_id)
    ).first()
    
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )
    
    # Create token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    role = user_role(user)
    school_name = user_school(user)
    access_token = create_access_token(
        data={"sub": user.username, "id": user.id, "role": role, "is_admin": user.is_admin, "is_super_admin": getattr(user, 'is_super_admin', False)},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "school_name": school_name if role != "SUPER_ADMIN" else "",
            "role": role,
            "class_assigned": getattr(user, "class_assigned", "") or "",
            "section_assigned": getattr(user, "section_assigned", "") or "",
            "is_admin": user.is_admin,
            "is_super_admin": getattr(user, 'is_super_admin', False),
            "dashboard_url": (
                "/static/super_admin.html" if role == "SUPER_ADMIN"
                else "/static/admin_dashboard.html" if role == "ADMIN"
                else "/static/teacher.html"
            )
        }
    }


# =========================
# Logout (client-side token removal)
# =========================
@router.post("/logout")
def logout():
    """Logout - client should remove the token"""
    return {"ok": True, "message": "Logged out successfully"}


# =========================
# Get Current User
# =========================
@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current logged-in user info"""
    return current_user


# =========================
# Create User (Admin only)
# =========================
@router.post("/users", response_model=UserResponse)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """Create a new user with strict role/school isolation."""
    # Check if username exists
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Check if email exists
    if user_data.email and db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )
    
    actor_role = user_role(admin)
    requested_role = (user_data.role or "TEACHER").strip().upper()
    if requested_role not in {"TEACHER", "ADMIN"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role. Allowed: TEACHER or ADMIN",
        )
    if actor_role != "SUPER_ADMIN" and requested_role != "TEACHER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can create admin accounts",
        )

    school_name = (user_data.school_name or user_school(admin) or user_data.full_name or "").strip()
    if requested_role == "ADMIN":
        if not school_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="School name is required for admin accounts",
            )
        existing_admin = db.query(User).filter(
            User.role == "ADMIN",
            User.school_name == school_name,
        ).first()
        if existing_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Admin already exists for school '{school_name}'",
            )
    full_name = (user_data.full_name or user_data.username).strip()
    class_assigned = (user_data.class_assigned or "").strip()
    section_assigned = (user_data.section_assigned or "").strip()

    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=full_name,
        role=requested_role,
        school_name=school_name,
        class_assigned=class_assigned if requested_role == "TEACHER" else "",
        section_assigned=section_assigned if requested_role == "TEACHER" else "",
        is_admin=requested_role == "ADMIN",
        is_super_admin=False,
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user


# =========================
# List Users (Admin only)
# =========================
@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user)
):
    """List all users (admin only)"""
    if user_role(admin) == "SUPER_ADMIN":
        users = db.query(User).all()
    else:
        users = db.query(User).filter(User.school_name == user_school(admin)).all()
    return users


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target_role = user_role(target)
    actor_role = user_role(admin)
    if target_role == "SUPER_ADMIN":
        raise HTTPException(status_code=400, detail="Cannot delete super admin")
    if actor_role != "SUPER_ADMIN":
        if target_role != "TEACHER":
            raise HTTPException(status_code=403, detail="Admin can only delete teacher accounts")
        if user_school(target) != user_school(admin):
            raise HTTPException(status_code=403, detail="Cannot delete users from another school")
    db.delete(target)
    db.commit()
    return {"ok": True, "message": "User deleted"}


# =========================
# Change Password
# =========================
@router.post("/change-password")
def change_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Change current user password"""
    # Verify old password
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect"
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return {"ok": True, "message": "Password changed successfully"}


# =========================
# Setup Default Admin (One-time)
# =========================
@router.post("/setup-admin")
def setup_admin(
    username: str = Form("superadmin@gmail.com"),
    password: str = Form("superadmin123"),
    db: Session = Depends(get_db)
):
    """Create default super admin user (one-time setup, only works if no users exist)"""
    # Check if any users exist
    if db.query(User).first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed. Use admin panel to create users."
        )
    
    # Validate credentials
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters"
        )

    # Create super admin user
    admin_user = User(
        username=username,
        email=username,
        hashed_password=get_password_hash(password),
        full_name="Super Administrator",
        role="SUPER_ADMIN",
        school_name="",
        is_active=True,
        is_admin=True,
        is_super_admin=True
    )
    
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)
    
    return {
        "ok": True,
        "message": "Super Admin created. Login with superadmin@gmail.com and your password.",
        "username": username,
    }


# =========================
# Create School Admin (Super Admin only)
# =========================
# SUPER_ADMIN_SECRET — must be set via environment variable SUPER_ADMIN_SECRET.
# Never hardcode this in source code. Change it immediately if exposed.
SUPER_ADMIN_SECRET = os.environ.get("SUPER_ADMIN_SECRET", "")
if not SUPER_ADMIN_SECRET:
    import secrets as _secrets
    SUPER_ADMIN_SECRET = _secrets.token_hex(32)  # random per-process if not configured

@router.post("/create-school-admin")
def create_school_admin(
    username: str = Form(...),
    password: str = Form(...),
    school_name: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Create a school admin — requires JWT with SUPER_ADMIN role."""
    if user_role(admin) != "SUPER_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin only",
        )
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    school_name = (school_name or "").strip()
    if not school_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="School name is required",
        )
    existing_school_admin = db.query(User).filter(
        User.role == "ADMIN",
        User.school_name == school_name,
    ).first()
    if existing_school_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Admin already exists for school '{school_name}'",
        )

    new_admin = User(
        username=username,
        email=username,
        hashed_password=get_password_hash(password),
        full_name=school_name,
        role="ADMIN",
        school_name=school_name,
        is_active=True,
        is_admin=True
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return {
        "ok": True,
        "message": "School admin created",
        "username": username,
        "user_id": new_admin.id,
        "school_name": new_admin.school_name,
    }


# =========================
# Super Admin Stats
# =========================
SUPER_ADMIN_SECRET_KEY = SUPER_ADMIN_SECRET  # Reuse same env-backed secret

@router.get("/super-stats")
def super_stats(secret: str, db: Session = Depends(get_db)):
    """Get platform stats — legacy secret-key auth (deprecated, prefer /super-stats-full with JWT)."""
    # Constant-time comparison to prevent timing attacks
    import hmac
    if not hmac.compare_digest(secret, SUPER_ADMIN_SECRET_KEY):
        raise HTTPException(status_code=403, detail="Forbidden")
    from app.models import Student, Attendance
    return {
        "admins": db.query(User).filter(User.is_admin == True).count(),
        "students": db.query(Student).count(),
        "attendance": db.query(Attendance).count()
    }


# =========================
# Super Admin Full Stats (JWT-protected)
# =========================
@router.get("/super-stats-full")
def super_stats_full(
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """
    Full platform analytics for the Super Admin dashboard.
    Returns per-school breakdown + platform totals. JWT protected.
    """
    from app.models import Student, Attendance
    from datetime import date, timedelta
    from sqlalchemy import func as sqlfunc

    if user_role(admin) != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Super admin only")

    today = date.today()

    # Platform totals
    total_schools = db.query(User).filter(User.role == "ADMIN").count()
    total_teachers = db.query(User).filter(User.role == "TEACHER").count()
    total_students = db.query(Student).count()
    total_attendance = db.query(Attendance).count()
    present_today = db.query(Attendance).filter(
        Attendance.date == today, Attendance.status == "P"
    ).count()

    # Per-school breakdown
    school_admins = db.query(User).filter(User.role == "ADMIN").all()
    schools = []
    for adm in school_admins:
        sn = adm.school_name or adm.full_name or adm.username
        s_count = db.query(Student).filter(Student.school_name == sn).count()
        p_today = db.query(Attendance).join(
            Student, Attendance.student_id == Student.id
        ).filter(
            Student.school_name == sn,
            Attendance.date == today,
            Attendance.status == "P",
        ).count()
        schools.append({
            "school_name": sn,
            "admin_username": adm.username,
            "admin_id": adm.id,
            "students": s_count,
            "present_today": p_today,
        })

    # All users list
    all_users = db.query(User).order_by(User.role, User.school_name).all()
    users_list = [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "full_name": u.full_name or u.username,
            "role": u.role or ("SUPER_ADMIN" if u.is_super_admin else "ADMIN"),
            "school_name": u.school_name or "",
            "class_assigned": u.class_assigned or "",
            "section_assigned": u.section_assigned or "",
            "is_active": u.is_active,
        }
        for u in all_users
    ]

    return {
        "ok": True,
        "platform": {
            "total_schools": total_schools,
            "total_teachers": total_teachers,
            "total_students": total_students,
            "total_attendance": total_attendance,
            "present_today": present_today,
            "today": str(today),
        },
        "schools": schools,
        "users": users_list,
    }


@router.patch("/users/{user_id}")
def update_user_status(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Update user status/details with role-aware access control."""
    actor_role = user_role(admin)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target_role = user_role(target)

    if actor_role == "SUPER_ADMIN":
        if target_role == "SUPER_ADMIN":
            raise HTTPException(status_code=400, detail="Cannot modify a super admin")
    else:
        if target_role != "TEACHER":
            raise HTTPException(status_code=403, detail="Admin can only edit teacher accounts")
        if user_school(target) != user_school(admin):
            raise HTTPException(status_code=403, detail="Cannot modify users from another school")

    if user_update.is_active is not None:
        target.is_active = user_update.is_active
    if user_update.full_name is not None:
        full_name = user_update.full_name.strip()
        if not full_name:
            raise HTTPException(status_code=400, detail="Full name cannot be empty")
        target.full_name = full_name
    if user_update.class_assigned is not None:
        if target_role != "TEACHER":
            raise HTTPException(status_code=400, detail="Class assignment is only valid for teachers")
        target.class_assigned = user_update.class_assigned.strip()
    if user_update.section_assigned is not None:
        if target_role != "TEACHER":
            raise HTTPException(status_code=400, detail="Section assignment is only valid for teachers")
        target.section_assigned = user_update.section_assigned.strip()
    db.commit()
    db.refresh(target)
    return {
        "ok": True,
        "message": f"User {target.username} updated",
        "is_active": target.is_active,
        "user": {
            "id": target.id,
            "full_name": target.full_name,
            "class_assigned": target.class_assigned or "",
            "section_assigned": target.section_assigned or "",
        },
    }


@router.delete("/super-delete-user/{user_id}")
def super_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Super admin: delete any user except other super admins."""
    if user_role(admin) != "SUPER_ADMIN":
        raise HTTPException(status_code=403, detail="Super admin only")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user_role(target) == "SUPER_ADMIN":
        raise HTTPException(status_code=400, detail="Cannot delete a super admin")
    db.delete(target)
    db.commit()
    return {"ok": True, "message": f"User {target.username} deleted"}
