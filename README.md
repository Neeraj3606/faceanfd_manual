# Face Attendance System

A modern, secure, and commercially-free face recognition-based attendance system with anti-spoofing protection and AI-powered insights. Built using **FastAPI**, **YuNet + SFace (OpenCV Zoo ONNX)**, **MiniFASNet v2 (Liveness Detection)**, and **Grok (xAI API)**.

---

## 🌟 Key Features

1. **Commercially-Free Face Recognition**
   - Uses **YuNet** for fast & accurate face detection (~390 KB) and **SFace** for face recognition (~37 KB) from the OpenCV Zoo.
   - 100% commercially usable (MIT License).
   - Fast, CPU-friendly inference running completely locally without heavy framework dependencies (like PyTorch or TensorFlow).

2. **Multi-Layer Anti-Spoofing & Liveness Detection**
   - **MiniFASNet v2 (ONNX)**: Local CPU-based liveness verification. Real faces are distinguished from printed photos and digital screens.
   - **Multi-Scale Inference**: Runs liveness scoring across multiple crop scales (e.g., 2.0x, 2.5x, 3.0x) to aggregate robust liveness decisions, minimizing false positives on mobile/tablet cameras.
   - **Texture Heuristics**: Secondary checks checking Laplacian variance (sharpness), contrast, color variance, and edge density to catch obvious flat media.
   - **Fail-Closed Configuration**: If the liveness model is missing or fails, the system automatically rejects verification for maximum security.

3. **Multi-Role Access Control (RBAC)**
   - **Super Admin**: High-level dashboard to create schools, manage school administrators, view global system stats, and configure global system-wide settings.
   - **School Admin**: Manage teacher accounts, enroll students with photos, configure school settings, and view school-wide attendance/excel reports.
   - **Teacher**: Take live face attendance via webcam/mobile camera, record manual/bulk attendance for students, track class analytics, and export reports.

4. **AI-Powered Insights (Powered by Grok)**
   - Fully integrated with the **Grok (xAI API)** to provide intelligent, natural-language analysis of attendance trends.
   - **Automatic Narrative Bullet Points**: Custom prompts tailored for Teachers (class-specific summaries, identifying students with <75% attendance) and Admins (school-wide performance, identifying worst/best performing classes).
   - **Natural Language Q&A**: Interactive chat grounded in the attendance database. Users can ask questions like "Who was absent on Monday?" or "Which class has the lowest attendance this month?" and get precise answers.

5. **Production-Ready & Highly Mobile-Responsive**
   - Fully optimized Frontend using modern Vanilla HTML/CSS/JS (glassmorphic aesthetic, viewport-fit=cover support for notch screens, large touch targets, PWA-ready for mobile install).
   - Local data isolation (different school codes/IDs are cryptographically hashed so student codes can overlap between schools securely).

6. **Excel Reports**
   - Fast and complete export of attendance sheets for a single day, custom date ranges, or monthly/periodical summaries with styled headers and automatic formatting.

---

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python 3.11)
- **Database**: SQLite (SQLAlchemy ORM with automatic tables & columns migration on startup)
- **Face Detection**: YuNet ONNX (MIT License)
- **Face Recognition**: SFace ONNX (MIT License)
- **Liveness Detection**: MiniFASNet v2 ONNX
- **AI Analytics**: Grok (xAI API) via `requests`
- **Frontend**: Glassmorphism CSS, Vanilla ES6 JavaScript (No bulky frameworks)

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11 (Python 3.12/3.13 are compatible, but 3.11 is recommended for local environments)
- Camera/Webcam (for live attendance marking)
- ~4GB RAM minimum

### 2. Installation
Clone the repository and install the dependencies:
```bash
# Enter the project directory
cd face_attendance_updated

# Create a virtual environment
python3.11 -m venv .venv311
source .venv311/bin/activate  # On Windows: .venv311\Scripts\activate

# Install required dependencies
pip install -r requirements.txt
```

### 3. Download AI Models
To automatically fetch the YuNet, SFace, and MiniFASNet ONNX models to the `data/models/` directory:
```bash
python download_model.py
```

### 4. Configuration
Create a `.env` file in the root directory (you can copy/rename `.env` if it already exists) and populate it:
```env
SECRET_KEY=your_generated_jwt_secret_key
SUPER_ADMIN_SECRET=your_generated_super_admin_secret_key
DATABASE_URL=sqlite:///data/attendance.db

# Face Recognition Settings
MATCH_THRESHOLD=0.65            # Cosine similarity matching threshold (0.55-0.70)

# Anti-Spoofing Settings
LIVENESS_ENABLED=true           # Enable liveness detection
MINIFASNET_REAL_THRESHOLD=0.20  # Real face score threshold
MINIFASNET_CROP_SCALE=2.2
MINIFASNET_SCALES=2.0,2.5,3.0
MINIFASNET_MULTI_SCALE=true     # Use multi-scale liveness scoring
LIVENESS_FAIL_CLOSED=true       # Fail closed for maximum security

# Grok AI Insights Configuration
GROK_API_KEY=your_xai_grok_api_key_here
GROK_MODEL=grok-3               # e.g., grok-2 or grok-3

# CORS Config
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```
> **Tip:** You can generate a strong secure key using:
> `python -c "import secrets; print(secrets.token_hex(32))"`

### 5. Running the Server
You can launch the FastAPI server using the production wrapper script, which runs environment & database diagnostics on launch:
```bash
python start_server.py
```
Or, start it directly using Uvicorn (or Conda if running in `saas311` environment):
```bash
# Direct run
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Open **http://localhost:8000** in your browser (it will automatically redirect you to the login screen).

---

## 🔑 Default Roles & Access

| Role | Default Username | Default Password | URL Route / Page |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `superadmin` / `superadmin@faceattend.local` | Found in Database setup (configured via `setup-admin` endpoint) | `/static/super_admin.html` |
| **School Admin** | Created by Super Admin | Created by Super Admin | `/static/admin_dashboard.html` |
| **Teacher** | Created by School Admin | Created by School Admin | `/static/teacher.html` |

---

## 📂 Project Structure

```text
face_attendance_updated/
├── app/
│   ├── main.py              # FastAPI main application & server launch wrapper
│   ├── routes.py            # Main API routing (attendance, analytics, student profile)
│   ├── auth_routes.py       # Authentication, user management, and super admin control
│   ├── auth.py              # JWT authentication & session verification utilities
│   ├── db.py                # Database connection & session setup
│   ├── models.py            # SQLAlchemy SQLite schema models (User, Student, Attendance, FaceEncoding)
│   ├── encoder.py           # YuNet + SFace face detection & recognition pipeline
│   ├── liveness.py          # MiniFASNet v2 multi-scale ONNX liveness engine
│   ├── antispoofing_onnx.py # Secondary texture quality/heuristic checks
│   ├── ai_insights.py       # Grok Q&A and narrative text analysis context builder
│   ├── attendance_excel.py  # Advanced multi-period/daily Excel spreadsheet builder
│   ├── storage.py           # Local file structure management
│   └── storage_helper.py    # General helper utilities
├── Frontend/
│   ├── login.html           # Modern responsive login page with safe areas
│   ├── super_admin.html     # Super admin management cockpit
│   ├── admin_dashboard.html # School administrator management dashboard
│   ├── teacher.html         # Classroom attendance capture and student panel
│   └── ...                  # Frontend visual styles and assets
├── data/
│   ├── attendance.db        # Live SQLite local database file
│   └── models/              # Downloaded ONNX model binaries (YuNet, SFace, MiniFASNet)
├── uploads/
│   └── students/            # Structured enrollments directory for student face images
├── requirements.txt         # Pip dependency requirements
├── start_server.py          # Interactive production server runner
└── .env                     # Server local environment variables
```

---

## 📡 API Reference & Endpoints

Interactive Swagger documentation is available locally at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Authentication
- `POST /auth/login` - User login session creation
- `POST /auth/logout` - User logout session termination
- `GET /auth/me` - Fetch authenticated user details
- `POST /auth/change-password` - Change account password

### Student & Face Registration
- `POST /enroll` - Enroll a student with structural face image data
- `DELETE /student/delete/{student_id}` - Clear student profile and face templates
- `GET /students` - List school-scoped/class-scoped students

### Attendance Operations
- `POST /attendance/mark` - Mark live face attendance (includes liveness detection check)
- `POST /attendance/manual` - Log/Update student attendance manually
- `POST /attendance/bulk` - Log/Update student attendance in bulk

### Reporting & Analytics
- `GET /attendance/today` - Today's class dashboard statistics
- `GET /attendance/export/today` - Export today's attendance roster to Excel
- `GET /attendance/export/excel` - Export custom range attendance sheet to Excel
- `GET /attendance/export/summary` - Export monthly summary report to Excel
- `GET /analytics/summary` - Overall metrics overview
- `GET /analytics/defaulters` - List students dropping below 75% attendance

### AI Insights (Grok)
- `GET /ai/insights` - Request auto-generated, role-specific text insights
- `POST /ai/chat` - Grounded attendance question and answer session
- `GET /ai/status` - Probe if Grok AI integration is ready & active

---

## 🔧 Troubleshooting

### 1. Camera Permissions
- Ensure that the browser has webcam access.
- Live camera attendance requires an SSL certificate (HTTPS) or running from `localhost`/`127.0.0.1`. Modern browsers restrict camera access on standard HTTP links.

### 2. Liveness Fails or False Rejections
- Ensure proper lighting on the face. Backlight or heavy shadows can trigger anti-spoofing flags.
- If anti-spoofing is too restrictive for your webcam quality, adjust `MINIFASNET_REAL_THRESHOLD` in `.env` (e.g., lower to `0.15` or `0.18`).
- If liveness models are missing, run: `python download_model.py`.

### 3. Face Recognition Mismatches
- If the system registers another student's face instead of the correct one, increase `MATCH_THRESHOLD` in `.env` (e.g., `0.70` or `0.75`).
- Ensure students enroll with at least 8 high-quality photos covering various angles/light profiles.

---

## 🔒 Security Practices
- **Password Hashing**: Bcrypt verification with dynamic salting.
- **JWT Authentication**: Cryptographically signed access tokens for stateless session tracking.
- **Data Isolation**: School-scoped database queries to keep student rosters isolated.
- **ORM Integrity**: Full SQLAlchemy representation preventing SQL Injection.

---

## 📄 License
This project is licensed under the **MIT License** — free for personal, educational, and commercial purposes.

---

## 🌟 Acknowledgements
- **OpenCV Zoo** for providing YuNet and SFace models.
- **MiniFASNet** authors for the anti-spoofing network architecture.
- **x.ai** for the Grok language model.
