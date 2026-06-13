# Face Attendance System — Dockerfile for Render Deployment
# ============================================================
# MiniFASNet anti-spoofing model is committed in the repo (1.7MB)
# so NO PyTorch needed in Docker — fast build, small image!
# YuNet + SFace are downloaded from OpenCV Zoo during build (~38MB)
# ============================================================

FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Skip local venv bootstrap (not needed in Docker)
ENV FACE_ATTENDANCE_SKIP_VENV_BOOTSTRAP=1

WORKDIR /app

# Install system dependencies required by OpenCV and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire project (includes data/models/minifasnet_v2.onnx from repo)
COPY . .

# Download YuNet + SFace from OpenCV Zoo (fast, ~38MB total)
# MiniFASNet is already in the repo — no download needed!
RUN python download_model.py

# Create uploads and data directories with proper permissions
RUN mkdir -p uploads/students data/models && \
    chmod -R 777 uploads data

# Expose the port (Render sets PORT env var, default to 8000)
EXPOSE 8000

# Start the application — Render provides PORT env variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
