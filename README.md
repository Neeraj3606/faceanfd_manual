# Face Attendance System

A server-side face recognition attendance platform with liveness detection and AI-powered reporting. Built with **FastAPI**, **PostgreSQL**, **YuNet + SFace (OpenCV Zoo)**, **MiniFASNet v2**, and **Grok (xAI)**.

---

## Key Features

**Commercially-Free Face Recognition**
Uses YuNet for face detection and SFace for face embedding — both MIT-licensed ONNX models from OpenCV Zoo. Inference runs entirely on CPU without PyTorch or TensorFlow.

**Anti-Spoofing and Liveness Detection**
MiniFASNet v2 (ONNX) performs local liveness verification against printed photos and screen replays. Multi-scale crop inference aggregates scores across multiple bounding box scales to reduce false rejections on mobile cameras. A secondary texture heuristic layer checks sharpness, edge density, and color saturation. When the liveness model is unavailable, the system rejects verification by default (fail-closed).

**Role-Based Access Control**
Three access tiers with isolated data scopes:
- Super Admin — manages schools, creates administrators, views global statistics.
- School Admin — manages teacher accounts, enrolls students, configures school settings, exports reports.
- Teacher — captures live face attendance, records manual or bulk entries, tracks class-level analytics.

**AI Insights via Grok**
Integrates with the Grok (xAI) API to generate role-specific narrative summaries and support natural-language queries against attendance data. Teachers receive class-level analysis; administrators receive school-wide performance breakdowns.

**Mobile-Responsive Frontend**
Vanilla HTML/CSS/JS frontend with PWA support, viewport-fit coverage for notched displays, and large touch targets. No external UI framework dependencies.

**Excel Reporting**
Exports daily rosters, custom date-range sheets, and monthly summary reports with auto-formatted column widths and styled headers.

---

## Tech Stack

| Component | Technology |
| :--- | :--- |
| Backend | FastAPI (Python 3.11) |
| Database | PostgreSQL via SQLAlchemy ORM |
| Face Detection | YuNet ONNX (MIT) |
| Face Recognition | SFace ONNX (MIT) |
| Liveness Detection | MiniFASNet v2 ONNX (Apache 2.0) |
| AI Analytics | Grok (xAI API) |
| Frontend | Vanilla HTML / CSS / ES6 JavaScript |

---

## Getting Started

### Prerequisites
- Python 3.11 or later
- A webcam or device camera for live attendance
- 4 GB RAM minimum
- PostgreSQL database (local or managed, e.g. Render)

### Installation

```bash
git clone https://github.com/your-org/face-attendance.git
cd face-attendance

python3.11 -m venv .venv311
source .venv311/bin/activate        # Windows: .venv311\Scripts\activate

pip install -r requirements.txt
```

### Downloading Models

YuNet and SFace are fetched from OpenCV Zoo. MiniFASNet is already included in the repository.

```bash
python download_model.py
```

### Configuration

Create a `.env` file in the project root. A sample structure is shown below — **do not commit real credentials**.

```env
# Security
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
SUPER_ADMIN_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">

# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Face Recognition
MATCH_THRESHOLD=0.65

# Liveness Detection
LIVENESS_ENABLED=true
LIVENESS_FAIL_CLOSED=true
MINIFASNET_REAL_THRESHOLD=0.20
MINIFASNET_CROP_SCALE=2.2
MINIFASNET_SCALES=2.0,2.5,3.0
MINIFASNET_MULTI_SCALE=true

# Grok AI (optional)
GROK_API_KEY=<your xAI API key>
GROK_MODEL=grok-3

# CORS (comma-separated allowed origins)
ALLOWED_ORIGINS=http://localhost:8000,https://yourdomain.com
```

### Running the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` — the root path redirects to the login page.

---

## Default Credentials

| Role | Username | Password |
| :--- | :--- | :--- |
| Super Admin | `super_admin` | Set via `_ensure_super_admin` on first run |
| School Admin | Created by Super Admin | Created by Super Admin |
| Teacher | Created by School Admin | Created by School Admin |

> Change the default Super Admin password immediately after first login.

---

## Project Structure

```
face_attendance/
├── app/
│   ├── routes.py              # Attendance, analytics, student API endpoints
│   ├── auth_routes.py         # Authentication and user management endpoints
│   ├── auth.py                # JWT utilities and password hashing
│   ├── db.py                  # Database engine and session configuration
│   ├── models.py              # SQLAlchemy ORM models
│   ├── encoder.py             # YuNet + SFace inference pipeline
│   ├── liveness.py            # MiniFASNet v2 ONNX liveness engine
│   ├── ai_insights.py         # Grok context builder and Q&A handler
│   ├── attendance_excel.py    # Excel report generation
│   ├── config.py              # Environment variable parsing
│   ├── storage.py             # Directory management
│   └── storage_helper.py      # File and path utilities
├── Frontend/
│   ├── login.html             # Login page
│   ├── super_admin.html       # Super admin dashboard
│   ├── admin_dashboard.html   # School admin dashboard
│   └── teacher.html           # Teacher attendance capture
├── data/
│   └── models/                # ONNX model binaries
├── uploads/
│   └── students/              # Enrolled student face images
├── main.py                    # Application entry point and lifespan hooks
├── download_model.py          # Model download and PTH-to-ONNX conversion
├── requirements.txt
└── Dockerfile
```

---

## API Reference

Full interactive documentation is available at `/docs` (Swagger UI) and `/redoc` when the server is running.

### Authentication
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | `/auth/login` | Create a session token |
| POST | `/auth/logout` | Invalidate the session |
| GET | `/auth/me` | Return the authenticated user profile |
| POST | `/auth/change-password` | Update account password |

### Student Management
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | `/enroll` | Enroll a student with face images |
| DELETE | `/student/delete/{student_id}` | Remove a student and their face data |
| GET | `/students` | List students scoped to the caller's role |

### Attendance
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | `/attendance/mark` | Record live face attendance (includes liveness check) |
| POST | `/attendance/manual` | Record or update a single attendance entry |
| POST | `/attendance/bulk` | Record or update attendance for multiple students |
| GET | `/attendance/today` | Return today's attendance records |
| GET | `/attendance/export/today` | Download today's roster as an Excel file |
| GET | `/attendance/export/excel` | Download a date-range attendance sheet |
| GET | `/attendance/export/summary` | Download a monthly summary report |

### Analytics
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | `/analytics/summary` | Overall attendance metrics |
| GET | `/analytics/class-wise` | Per-class attendance percentages |
| GET | `/analytics/monthly` | Daily trend for the current month |
| GET | `/analytics/defaulters` | Students below a configurable attendance threshold |

### AI Insights
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | `/ai/insights` | Generate role-specific narrative summary |
| POST | `/ai/chat` | Answer a natural-language question about attendance data |
| GET | `/ai/status` | Check if Grok integration is configured and active |

---

## Deployment on Render

1. Create a **Web Service** pointing to your GitHub repository.
2. Set **Environment** to `Docker`.
3. Configure the following environment variables in the Render dashboard:

| Variable | Description |
| :--- | :--- |
| `DATABASE_URL` | Render PostgreSQL internal connection string |
| `SECRET_KEY` | Random 32-byte hex string |
| `SUPER_ADMIN_SECRET` | Random 32-byte hex string |
| `LIVENESS_ENABLED` | `true` |
| `LIVENESS_FAIL_CLOSED` | `true` |
| `ALLOWED_ORIGINS` | Your Render service URL |
| `GROK_API_KEY` | Optional — enables AI insights |

4. The application creates all database tables and runs safe column migrations on startup.
5. The Super Admin account is created automatically on the first startup if no Super Admin exists.

---

## Troubleshooting

**Camera access denied in browser**
Live attendance requires camera access over HTTPS or from `localhost`. Standard HTTP connections are blocked by browsers for camera APIs.

**Liveness false rejections**
Poor or backlit lighting commonly triggers anti-spoofing flags. Lower `MINIFASNET_REAL_THRESHOLD` to `0.15` or `0.18` in `.env` if legitimate faces are being rejected in your environment.

**Face recognition mismatches**
Increase `MATCH_THRESHOLD` to `0.70` or higher if the system is producing incorrect matches. Enroll each student with a minimum of eight photos covering different angles and lighting conditions.

---

## Security Notes

- Passwords are hashed with bcrypt.
- Sessions use short-lived, cryptographically signed JWTs.
- All database queries are parameterized through SQLAlchemy to prevent SQL injection.
- Student data is scoped per school using a SHA-1-derived identifier to prevent cross-school data leakage.
- Never commit `.env` or credentials to version control.

---

## License

MIT License. Free for personal, educational, and commercial use.

---

## Acknowledgements

- OpenCV Zoo for YuNet and SFace ONNX models.
- MiniFASNet authors for the Silent-Face-Anti-Spoofing architecture.
- xAI for the Grok language model API.
