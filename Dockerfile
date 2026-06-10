# Face Attendance System - Dockerfile for Render Deployment
# Uses Python 3.11 slim with OpenCV and ONNX Runtime dependencies

FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Skip local venv bootstrap (not needed in Docker)
ENV FACE_ATTENDANCE_SKIP_VENV_BOOTSTRAP=1

# Set working directory
WORKDIR /app

# Install system dependencies required by OpenCV and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Download the required ONNX face recognition and liveness models
RUN python download_model.py

# Create uploads directory (writable for face photo uploads)
# data/ is NOT needed for PostgreSQL deployments
RUN mkdir -p uploads/students && \
    chmod -R 777 uploads

# Expose the port (Render sets PORT env var, default to 8000)
EXPOSE 8000

# Start the application — Render provides PORT env variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
