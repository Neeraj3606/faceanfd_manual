#!/usr/bin/env python3
"""
Clean all test data from database
Removes all students, attendance records, and test users
Keeps only super admin
"""

import sqlite3
import os
import shutil

DB_PATH = 'data/attendance.db'
ENCODINGS_PATH = 'data/encodings.pkl'
UPLOADS_DIR = 'uploads/students'

def clean_database():
    """Clean all test data from database"""
    print("=" * 70)
    print("CLEANING DATABASE")
    print("=" * 70)
    
    if not os.path.exists(DB_PATH):
        print("❌ Database not found")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Count before deletion
    cursor.execute("SELECT COUNT(*) FROM students")
    student_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM attendance")
    attendance_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_super_admin = 0")
    user_count = cursor.fetchone()[0]
    
    print(f"\nCurrent data:")
    print(f"  Students: {student_count}")
    print(f"  Attendance records: {attendance_count}")
    print(f"  Users (non-super-admin): {user_count}")
    
    # Ask for confirmation
    response = input("\n⚠️  Delete all this data? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Cancelled")
        conn.close()
        return
    
    print("\n🗑️  Deleting data...")
    
    # Delete attendance records
    cursor.execute("DELETE FROM attendance")
    print(f"✓ Deleted {attendance_count} attendance records")
    
    # Delete students
    cursor.execute("DELETE FROM students")
    print(f"✓ Deleted {student_count} students")
    
    # Delete non-super-admin users
    cursor.execute("DELETE FROM users WHERE is_super_admin = 0")
    print(f"✓ Deleted {user_count} users")
    
    conn.commit()
    conn.close()
    
    # Delete encodings file
    if os.path.exists(ENCODINGS_PATH):
        os.remove(ENCODINGS_PATH)
        print(f"✓ Deleted encodings file")
    
    # Delete uploads directory
    if os.path.exists(UPLOADS_DIR):
        shutil.rmtree(UPLOADS_DIR)
        os.makedirs(UPLOADS_DIR)
        print(f"✓ Cleaned uploads directory")
    
    print("\n" + "=" * 70)
    print("✅ DATABASE CLEANED SUCCESSFULLY")
    print("=" * 70)
    print("\nSuper admin account is preserved.")
    print("You can now create fresh schools, teachers, and students.")
    print("\nRestart server: pkill -f start_server && python3 start_server.py")

if __name__ == "__main__":
    clean_database()
