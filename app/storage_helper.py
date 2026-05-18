"""
Storage helper functions for School/Class/Section structure
"""

import os
import shutil
from app.config import UPLOADS_DIR


def get_student_folder_path(school_name: str, class_name: str, section: str, student_id: str) -> str:
    """
    Get student folder path with School/Class/Section structure
    
    Args:
        school_name: School name
        class_name: Class name
        section: Section name
        student_id: Student ID
    
    Returns:
        str: Full path to student folder
    """
    # Clean names for folder structure
    school_clean = sanitize_folder_name(school_name or "Unknown_School")
    class_clean = sanitize_folder_name(class_name or "Unknown_Class")
    section_clean = sanitize_folder_name(section or "Unknown_Section")
    
    return os.path.join(UPLOADS_DIR, school_clean, class_clean, section_clean, str(student_id))


def sanitize_folder_name(name: str) -> str:
    """
    Sanitize folder name to remove invalid characters
    
    Args:
        name: Original name
    
    Returns:
        str: Sanitized name
    """
    # Remove or replace invalid characters
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '/', '\\']
    for char in invalid_chars:
        name = name.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    name = name.strip(' .')
    
    # Ensure it's not empty
    if not name:
        name = "Unknown"
    
    return name


def ensure_student_folder(school_name: str, class_name: str, section: str, student_id: str) -> str:
    """
    Create student folder if it doesn't exist
    
    Args:
        school_name: School name
        class_name: Class name
        section: Section name
        student_id: Student ID
    
    Returns:
        str: Path to student folder
    """
    folder_path = get_student_folder_path(school_name, class_name, section, student_id)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def list_student_images_new(school_name: str, class_name: str, section: str, student_id: str) -> list:
    """
    List student images from new folder structure
    
    Args:
        school_name: School name
        class_name: Class name
        section: Section name
        student_id: Student ID
    
    Returns:
        list: List of image file paths
    """
    from app.config import ALLOWED_EXTENSIONS
    
    folder = get_student_folder_path(school_name, class_name, section, student_id)
    if not os.path.isdir(folder):
        return []

    files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(ALLOWED_EXTENSIONS)
    ]
    files.sort()
    return files


def migrate_old_to_new_structure():
    """
    Migrate old student folders to new School/Class/Section structure
    This is a one-time migration function
    """
    print("🔄 Starting migration to new folder structure...")
    
    if not os.path.exists(UPLOADS_DIR):
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        print("✅ Uploads directory created")
        return
    
    migrated_count = 0
    
    for item in os.listdir(UPLOADS_DIR):
        old_student_path = os.path.join(UPLOADS_DIR, item)
        
        # Skip if it's not a directory or already in new structure
        if not os.path.isdir(old_student_path):
            continue
            
        # Check if this is an old student folder (direct student_id folder)
        if os.path.exists(os.path.join(old_student_path, "images")) or any(f.lower().endswith(('.jpg', '.jpeg', '.png')) for f in os.listdir(old_student_path)):
            print(f"📁 Migrating student: {item}")
            
            # This is an old student folder, migrate to new structure
            # For migration, we'll use default values for school, class, section
            school_name = "Default_School"
            class_name = "Default_Class"
            section = "Default_Section"
            
            new_folder = get_student_folder_path(school_name, class_name, section, item)
            
            # Create new folder structure
            os.makedirs(new_folder, exist_ok=True)
            
            # Move files
            for file_name in os.listdir(old_student_path):
                old_file = os.path.join(old_student_path, file_name)
                new_file = os.path.join(new_folder, file_name)
                
                if os.path.isfile(old_file):
                    shutil.move(old_file, new_file)
            
            # Remove old empty folder
            try:
                os.rmdir(old_student_path)
            except:
                pass  # Folder not empty, skip removal
            
            migrated_count += 1
    
    print(f"✅ Migration complete! Migrated {migrated_count} students")
