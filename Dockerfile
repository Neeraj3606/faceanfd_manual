# Face Attendance System - Dockerfile for Railway Deployment
# Uses Python 3.11 slim with OpenCV, InsightFace, and ONNX Runtime dependencies

FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies required by OpenCV wheels
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

# Create necessary directories and set permissions so non-root users (Render) can write to SQLite
RUN mkdir -p uploads/students data && \
    chmod -R 777 uploads data

# Expose the port (Railway sets PORT env var, but we default to 8000)
EXPOSE 8000

# Start the application
# Render/Railway provides PORT env variable, otherwise default to 8000
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
