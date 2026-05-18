"""
Excel Export for Face Attendance System
Client-side download functionality
"""

import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Attendance, Student
from fastapi.responses import StreamingResponse
import io


def _display_student_id(student: Student) -> str:
    return (getattr(student, "student_code", "") or student.id or "")


def export_attendance_excel(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    school_name: Optional[str] = None,
    class_name: Optional[str] = None,
    section: Optional[str] = None,
    student_ids: Optional[List[str]] = None
) -> StreamingResponse:
    """
    Export attendance data to Excel file for client download
    
    Returns:
        StreamingResponse: Excel file for browser download
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
    
    if school_name:
        query = query.filter(Student.school_name == school_name)
    
    if class_name:
        query = query.filter(Student.class_name == class_name)
    
    if section:
        query = query.filter(Student.section == section)
    
    if student_ids:
        query = query.filter(Attendance.student_id.in_(student_ids))
    
    # Order by date and student
    query = query.order_by(Attendance.date, Student.name)
    
    # Execute query
    results = query.all()
    
    if not results:
        # Create empty Excel with headers
        data = [{
            'Serial No': '',
            'Name': '',
            'Class': '',
            'Section': '',
            'Enroll ID': '',
            'Roll': '',
            'Date': '',
            'In Time': '',
            'Out Time': '',
            'Status': '',
            'Remarks': ''
        }]
    else:
        # Convert to DataFrame with proper column names
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
    
    # Create Excel file in memory
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
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
        
        # Add title rows with school and class info
        worksheet.insert_rows(1, amount=3)
        title_parts = ['Attendance Report']
        if school_name:
            title_parts.append(f'School: {school_name}')
        if class_name:
            title_parts.append(f'Class: {class_name}')
        if section:
            title_parts.append(f'Section: {section}')
        title_parts.append(f'Date: {start_date} to {end_date}')

        worksheet['A1'] = title_parts[0]
        worksheet.merge_cells('A1:K1')
        worksheet['A1'].font = worksheet['A1'].font.copy(bold=True, size=14)

        worksheet['A2'] = ' | '.join(title_parts[1:])
        worksheet.merge_cells('A2:K2')
        worksheet['A2'].font = worksheet['A2'].font.copy(bold=True, size=11)

        worksheet['A3'] = ''  # spacer row
    
    output.seek(0)
    
    # Generate filename
    filename = f"attendance_{start_date.strftime('%Y-%m-%d')}.xlsx"
    
    # Return as StreamingResponse for browser download
    return StreamingResponse(
        io.BytesIO(output.read()),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def export_today_attendance_excel(
    db: Session,
    school_name: Optional[str] = None,
    class_name: Optional[str] = None,
    section: Optional[str] = None
) -> StreamingResponse:
    """
    Export today's attendance to Excel for client download

    Returns:
        StreamingResponse: Excel file for browser download
    """
    today = date.today()
    return export_attendance_excel(
        db,
        start_date=today,
        end_date=today,
        school_name=school_name,
        class_name=class_name,
        section=section
    )


def generate_summary_excel(
    db: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    school_name: Optional[str] = None,
    class_name: Optional[str] = None,
    section: Optional[str] = None
) -> StreamingResponse:
    """
    Generate attendance summary Excel report for client download
    
    Returns:
        StreamingResponse: Excel file for browser download
    """
    
    if not start_date:
        start_date = date.today()
    if not end_date:
        end_date = date.today()
    
    # Get all students
    student_query = db.query(Student)
    
    if school_name:
        student_query = student_query.filter(Student.school_name == school_name)
    
    if class_name:
        student_query = student_query.filter(Student.class_name == class_name)
    
    if section:
        student_query = student_query.filter(Student.section == section)
    
    students = student_query.all()
    
    # Generate date range
    date_range = []
    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date)
        current_date += timedelta(days=1)
    
    # Create summary data
    summary_data = []
    serial_no = 1
    for student in students:
        row = {
            'Serial No': serial_no,
            'Enroll ID': _display_student_id(student),
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
        serial_no += 1
    
    df = pd.DataFrame(summary_data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Summary Report', index=False)
        
        # Format the summary sheet
        worksheet = writer.sheets['Summary Report']
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
        
        # Add title rows with school and class info
        worksheet.insert_rows(1, amount=3)
        title_parts = ['Attendance Summary']
        if school_name:
            title_parts.append(f'School: {school_name}')
        if class_name:
            title_parts.append(f'Class: {class_name}')
        if section:
            title_parts.append(f'Section: {section}')
        title_parts.append(f'Date: {start_date} to {end_date}')

        worksheet['A1'] = title_parts[0]
        worksheet.merge_cells('A1:L1')
        worksheet['A1'].font = worksheet['A1'].font.copy(bold=True, size=14)

        worksheet['A2'] = ' | '.join(title_parts[1:])
        worksheet.merge_cells('A2:L2')
        worksheet['A2'].font = worksheet['A2'].font.copy(bold=True, size=11)

        worksheet['A3'] = ''  # spacer row
    
    output.seek(0)
    
    # Generate filename
    filename = f"attendance_summary_{start_date.strftime('%Y-%m-%d')}_to_{end_date.strftime('%Y-%m-%d')}.xlsx"
    
    # Return as StreamingResponse for browser download
    return StreamingResponse(
        io.BytesIO(output.read()),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
