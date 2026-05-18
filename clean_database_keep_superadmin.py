#!/usr/bin/env python3
"""
Database Cleanup Script
- Keeps only super admin user
- Deletes all other users (teachers, admins)
- Deletes all students
- Deletes all attendance records
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from app.db import engine, SessionLocal
from app.models import User, Student, Attendance
from sqlalchemy import text

def clean_database():
    """Clean database keeping only super admin"""
    db = SessionLocal()
    
    try:
        print("🧹 Starting database cleanup...")
        
        # 1. Delete all attendance records
        attendance_count = db.query(Attendance).count()
        db.query(Attendance).delete()
        print(f"✅ Deleted {attendance_count} attendance records")
        
        # 2. Delete all students
        student_count = db.query(Student).count()
        db.query(Student).delete()
        print(f"✅ Deleted {student_count} students")
        
        # 3. Delete all users except super admin
        non_super_users = db.query(User).filter(User.is_super_admin == False).all()
        user_count = len(non_super_users)
        for user in non_super_users:
            db.delete(user)
        print(f"✅ Deleted {user_count} users (kept super admin)")
        
        # 4. Verify super admin exists
        super_admin = db.query(User).filter(User.is_super_admin == True).first()
        if super_admin:
            print(f"\n✅ Super Admin preserved:")
            print(f"   Username: {super_admin.username}")
            print(f"   Email: {super_admin.email}")
            print(f"   Role: {super_admin.role}")
        else:
            print("\n⚠️  WARNING: No super admin found in database!")
            print("   Creating default super admin...")
            from app.auth import get_password_hash
            new_super_admin = User(
                username="superadmin@gmail.com",
                email="superadmin@gmail.com",
                hashed_password=get_password_hash("superadmin123"),
                full_name="Super Administrator",
                role="SUPER_ADMIN",
                school_name="",
                is_active=True,
                is_admin=True,
                is_super_admin=True
            )
            db.add(new_super_admin)
            print(f"   ✅ Created super admin: superadmin@gmail.com / superadmin123")
        
        # Commit all changes
        db.commit()
        
        # 5. Final counts
        print("\n📊 Final Database State:")
        print(f"   Users: {db.query(User).count()} (1 super admin)")
        print(f"   Students: {db.query(Student).count()}")
        print(f"   Attendance: {db.query(Attendance).count()}")
        
        print("\n✅ Database cleanup completed successfully!")
        print("\n🔑 Login Credentials:")
        super_admin = db.query(User).filter(User.is_super_admin == True).first()
        if super_admin:
            print(f"   Username: {super_admin.username}")
            print(f"   Password: (use your existing password or reset if needed)")
        
    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("DATABASE CLEANUP - Keep Super Admin Only")
    print("=" * 60)
    print("\nThis will:")
    print("  ❌ Delete ALL attendance records")
    print("  ❌ Delete ALL students")
    print("  ❌ Delete ALL users except super admin")
    print("  ✅ Keep super admin account")
    print("\n" + "=" * 60)
    
    response = input("\nAre you sure you want to continue? (yes/no): ").strip().lower()
    
    if response == "yes":
        clean_database()
    else:
        print("\n❌ Cleanup cancelled.")
