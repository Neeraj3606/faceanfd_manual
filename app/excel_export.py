"""
Excel Export functionality for Face Attendance System
"""

import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Attendance, Student


def _display_student_id(student: Student) -> str:
    return (getattr(student, "student_code", "") or student.id or "")


def export_attendance_to_excel(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    class_name: Optional[str] = None,
    student_ids: Optional[List[str]] = None
) -> str:
    """
    Export attendance data to Excel file
    
    Args:
        db: Database session
        start_date: Start date for filter (default: today)
        end_date: End date for filter (default: today)
        class_name: Filter by class name
        student_ids: Filter by specific student IDs
    
    Returns:
        str: Path to generated Excel file
    """
    
    # Default to today if no dates provided
    if not start_date:
        start_date = date.today()
    if not end_date:
        end_date = date.today()
    
    # Build query
    query = db.query(Attendance, Student).join(Student)
    
    # Apply filters
    query = query.filter(Attendance.date >= start_date, Attendance.date <= end_date)
    
    if class_name:
        query = query.filter(Student.class_name == class_name)
    
    if student_ids:
        query = query.filter(Attendance.student_id.in_(student_ids))
    
    # Order by date and student
    query = query.order_by(Attendance.date, Student.name)
    
    # Execute query
    results = query.all()
    
    if not results:
        raise ValueError("No attendance records found for the given criteria")
    
    data = []
    serial_no = 1
    for attendance, student in results:
        data.append({
            'Serial No': serial_no,
            'Name': student.name,
            'Class': student.class_name,
            'Section': student.section,
            'Enroll ID': _display_student_id(student),
            'Roll': student.roll,
            'Date': attendance.date.strftime('%Y-%m-%d'),
            'In Time': attendance.in_time.strftime('%I:%M %p') if attendance.in_time else '',
            'Out Time': attendance.out_time.strftime('%I:%M %p') if attendance.out_time else '',
            'Status': attendance.status,
            'Remarks': attendance.remark or ''
        })
        serial_no += 1
    
    df = pd.DataFrame(data)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"attendance_report_{start_date}_to_{end_date}_{timestamp}.xlsx"
    filepath = f"/tmp/{filename}"
    
    # Create Excel writer with formatting
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Attendance Report', index=False)
        
        # Get the workbook and worksheet for formatting
        worksheet = writer.sheets['Attendance Report']
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Add header formatting
        for cell in worksheet[1]:
            cell.font = cell.font.copy(bold=True)
            cell.fill = cell.fill.copy(start_color='DDDDDD', end_color='DDDDDD')
    
    return filepath


def generate_summary_report(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    class_name: Optional[str] = None
) -> str:
    """
    Generate attendance summary report (present/absent counts)
    
    Args:
        db: Database session
        start_date: Start date for filter
        end_date: End date for filter
        class_name: Filter by class name
    
    Returns:
        str: Path to generated Excel file
    """
    
    if not start_date:
        start_date = date.today()
    if not end_date:
        end_date = date.today()
    
    # Get all students
    student_query = db.query(Student)
    if class_name:
        student_query = student_query.filter(Student.class_name == class_name)
    
    students = student_query.all()
    
    # Generate date range
    date_range = []
    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date)
        current_date += timedelta(days=1)
    
    # Create summary data
    summary_data = []
    for student in students:
        row = {
            'Student ID': _display_student_id(student),
            'Student Name': student.name,
            'Class': student.class_name,
            'Section': student.section,
            'Roll Number': student.roll
        }
        
        # Add attendance for each date
        total_days = len(date_range)
        present_days = 0
        absent_days = 0
        leave_days = 0
        half_days = 0
        
        for check_date in date_range:
            attendance = db.query(Attendance).filter(
                Attendance.student_id == student.id,
                Attendance.date == check_date
            ).first()
            
            if attendance:
                if attendance.status == 'P':
                    present_days += 1
                elif attendance.status == 'A':
                    absent_days += 1
                elif attendance.status in ['H', 'HD']:
                    half_days += 1
                elif attendance.status == 'L':
                    leave_days += 1
        
        row.update({
            'Total Days': total_days,
            'Present': present_days,
            'Absent': absent_days,
            'Half Day': half_days,
            'Leave': leave_days,
            'Attendance %': round((present_days / total_days) * 100, 2) if total_days > 0 else 0
        })
        
        summary_data.append(row)
    
    df = pd.DataFrame(summary_data)
    
    # Generate filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"attendance_summary_{start_date}_to_{end_date}_{timestamp}.xlsx"
    filepath = f"/tmp/{filename}"
    
    # Export to Excel
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Format the summary sheet
        worksheet = writer.sheets['Summary']
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Header formatting
        for cell in worksheet[1]:
            cell.font = cell.font.copy(bold=True)
            cell.fill = cell.fill.copy(start_color='DDDDDD', end_color='DDDDDD')
    
    return filepath
