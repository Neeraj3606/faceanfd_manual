# Face Attendance System

A modern, secure face recognition-based attendance system with anti-spoofing protection, built with FastAPI and InsightFace.

## Features

- **Face Recognition** - Fast and accurate student identification using InsightFace
- **Anti-Spoofing** - Multi-layer protection against photo/video attacks
- **Multi-Role Support** - Super Admin, Admin, and Teacher roles
- **Manual Attendance** - Backup option for technical issues
- **Excel Reports** - Export attendance data with filters
- **Multi-School Support** - Separate data for different schools/classes
- **PWA Support** - Install as mobile app
- **Offline Capable** - Works without internet after setup

## Tech Stack

- **Backend**: FastAPI (Python 3.11)
- **Database**: SQLite
- **Face Recognition**: InsightFace (ONNX Runtime)
- **Anti-Spoofing**: MiniFASNet + Custom checks
- **Frontend**: Vanilla JavaScript (no framework)

## Quick Start

### 1. Prerequisites

- Python 3.11
- Webcam
- 4GB RAM minimum

### 2. Installation

```bash
# Clone or download the project
cd face_attendance_updated

# Create virtual environment
python3.11 -m venv .venv311
source .venv311/bin/activate  # On Windows: .venv311\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create a `.env` file (or use existing):

```env
# Database
DATABASE_URL=sqlite:///data/attendance.db

# Face Recognition
MATCH_THRESHOLD=0.65

# Anti-Spoofing
LIVENESS_ENABLED=true
MINIFASNET_REAL_THRESHOLD=0.20
```

### 4. Run Server

```bash
python start_server.py
```

Server starts at: **http://localhost:8000**

### 5. Default Login

- **Username**: `admin`
- **Password**: `admin123`

## Usage

### For Super Admin

1. Login at `/static/super_admin.html`
2. Create schools and admin accounts
3. Manage system-wide settings

### For Admin

1. Login at `/static/admin_dashboard.html`
2. Create teacher accounts
3. Enroll students with photos
4. View school-wide reports

### For Teachers

1. Login at `/static/teacher.html`
2. Mark attendance (face or manual)
3. View class attendance
4. Export Excel reports

## API Documentation

Interactive API docs available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

```
POST   /auth/login              - User login
POST   /students/enroll         - Enroll new student
POST   /attendance/mark         - Mark attendance (face)
POST   /attendance/manual       - Mark attendance (manual)
GET    /attendance/export/today - Export today's attendance
GET    /attendance/export/excel - Export date range
```

## Project Structure

```
face_attendance_updated/
├── app/
│   ├── main.py              # FastAPI application
│   ├── routes.py            # API endpoints
│   ├── models.py            # Database models
│   ├── encoder.py           # Face recognition
│   ├── antispoofing_onnx.py # Anti-spoofing
│   └── config.py            # Configuration
├── Frontend/
│   ├── super_admin.html     # Super admin dashboard
│   ├── admin_dashboard.html # Admin dashboard
│   ├── teacher.html         # Teacher dashboard
│   └── login.html           # Login page
├── data/
│   ├── attendance.db        # SQLite database
│   └── models/              # AI models (auto-downloaded)
├── uploads/
│   └── students/            # Student photos
├── requirements.txt         # Python dependencies
├── start_server.py          # Server startup script
└── .env                     # Configuration
```

## Configuration Options

### Face Recognition

```env
MATCH_THRESHOLD=0.65          # Lower = stricter matching (0.4-0.8)
INSIGHTFACE_DET_WIDTH=320     # Detection width (lower = faster)
INSIGHTFACE_DET_HEIGHT=320    # Detection height
```

### Anti-Spoofing

```env
LIVENESS_ENABLED=true                # Enable/disable anti-spoofing
MINIFASNET_REAL_THRESHOLD=0.20       # Real face threshold (0.15-0.30)
MINIFASNET_MULTI_SCALE=true          # Multi-scale detection
LIVENESS_FAIL_CLOSED=true            # Reject on spoofing detection
```

### Performance

```env
WORKERS=4                     # Number of worker processes
TIMEOUT=60                    # Request timeout (seconds)
```

## Troubleshooting

### Camera not working?

- Check browser permissions
- Try different browser (Chrome recommended)
- Ensure HTTPS or localhost

### Face not recognized?

- Ensure good lighting
- Face camera directly
- Re-enroll with more photos
- Adjust `MATCH_THRESHOLD`

### Anti-spoofing too strict?

Lower the threshold:
```env
MINIFASNET_REAL_THRESHOLD=0.15
```

### Slow performance?

Reduce detection size:
```env
INSIGHTFACE_DET_WIDTH=240
INSIGHTFACE_DET_HEIGHT=240
```

## Deployment

### Production Server

```bash
# Install dependencies
pip install -r requirements.txt

# Run with gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### Docker

```bash
# Build image
docker build -t face-attendance .

# Run container
docker run -p 8000:8000 -v $(pwd)/data:/app/data face-attendance
```

### Systemd Service

Create `/etc/systemd/system/face-attendance.service`:

```ini
[Unit]
Description=Face Attendance System
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/face_attendance_updated
Environment="PATH=/path/to/.venv311/bin"
ExecStart=/path/to/.venv311/bin/python start_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable face-attendance
sudo systemctl start face-attendance
```

## Security

- **Password Hashing**: bcrypt with salt
- **JWT Tokens**: Secure session management
- **Role-Based Access**: Separate permissions for each role
- **Anti-Spoofing**: Multi-layer fake detection
- **SQL Injection**: Protected via SQLAlchemy ORM
- **XSS Protection**: Input sanitization

## Database Backup

```bash
# Backup
cp data/attendance.db data/backup_$(date +%Y%m%d).db

# Restore
cp data/backup_20260517.db data/attendance.db
```

## License

MIT License - Free for commercial and personal use

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review server logs: `tail -f nohup.out`
3. Check API docs: http://localhost:8000/docs

## Credits

- **InsightFace** - Face recognition models
- **FastAPI** - Web framework
- **ONNX Runtime** - Model inference
