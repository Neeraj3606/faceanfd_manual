from datetime import datetime, date as date_cls

from sqlalchemy import Column, Integer, String, DateTime, Date, Enum, Text, ForeignKey, Boolean, LargeBinary
from sqlalchemy.sql import func
from app.db import Base


# =========================
# Users Table (for login)
# =========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(String(30), nullable=False, default="TEACHER")
    school_name = Column(String(100), nullable=True, default="")
    class_assigned = Column(String(100), nullable=True, default="")
    section_assigned = Column(String(50), nullable=True, default="")
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_super_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.now)


# =========================
# Students Table
# =========================
class Student(Base):
    __tablename__ = "students"

    id = Column(String(50), primary_key=True, index=True, nullable=False)
    student_code = Column(String(50), index=True, nullable=True, default="")
    name = Column(String(255), nullable=False, default="")
    school_name = Column(String(100), nullable=False, default="")
    class_name = Column(String(100), nullable=False, default="")
    section = Column(String(50), nullable=False, default="")
    roll = Column(String(50), nullable=False, default="")


# =========================
# Attendance Table
# =========================
class Attendance(Base):
    __tablename__ = "attendance"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Foreign key to students table
    student_id = Column(String(50), ForeignKey('students.id', ondelete='CASCADE'), index=True, nullable=False)

    # Date column for attendance tracking
    date = Column(Date, nullable=False, default=date_cls.today)

    # Attendance status
    status = Column(
        Enum("P", "A", "H", "HD", "L", name="attendance_status", native_enum=False),
        default="A",
        nullable=False
    )

    # QR code tracking
    qr_code = Column(Integer, default=0, nullable=False)

    # Biometric method used
    biometric_method = Column(
        Enum("thumb", "iris", "face", name="biometric_method", native_enum=False),
        nullable=True
    )

    # RFID code
    rfid_code = Column(String(50), nullable=True)

    # Remarks
    remark = Column(Text, nullable=True)

    # Branch ID
    branch_id = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime,
        server_default=func.current_timestamp(),
        default=datetime.now,
        nullable=False
    )

    updated_at = Column(
        DateTime,
        nullable=True,
        onupdate=datetime.now
    )

    # Check-in and check-out times
    in_time = Column(DateTime, nullable=True)
    out_time = Column(DateTime, nullable=True)


# =========================
# Face Encodings Table
# =========================
class FaceEncoding(Base):
    __tablename__ = "face_encodings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey('students.id', ondelete='CASCADE'), index=True, nullable=False)
    student_name = Column(String(255), nullable=False, default="")
    encoding_blob = Column(LargeBinary, nullable=False)  # pickled numpy array
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.now)
