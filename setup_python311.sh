#!/bin/bash
# Setup script for Face Attendance System
# Python 3.11 + SQLite + Lightweight Anti-Spoofing

set -e  # Exit on error

echo "🚀 Face Attendance System Setup (Python 3.11)"
echo "=============================================="
echo ""

# Check Python 3.11
echo "📋 Checking Python 3.11..."
if ! command -v python3.11 &> /dev/null; then
    echo "❌ Python 3.11 not found!"
    echo ""
    echo "Please install Python 3.11:"
    echo "  macOS: brew install python@3.11"
    echo "  Linux: sudo apt install python3.11 python3.11-venv"
    exit 1
fi

PYTHON_VERSION=$(python3.11 --version)
echo "✅ Found: $PYTHON_VERSION"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment (.venv311)..."
if [ -d ".venv311" ]; then
    echo "⚠️  Virtual environment already exists. Removing old one..."
    rm -rf .venv311
fi

python3.11 -m venv .venv311
echo "✅ Virtual environment created"
echo ""

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv311/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip
echo "✅ pip upgraded"
echo ""

# Install requirements
echo "📥 Installing dependencies..."
echo "   This may take a few minutes..."
pip install -r requirements.txt
echo "✅ All dependencies installed"
echo ""

# Create necessary directories
echo "📁 Creating data directories..."
mkdir -p data/models/insightface
mkdir -p uploads/students
mkdir -p data/matplotlib
echo "✅ Directories created"
echo ""

# Check if InsightFace models exist
echo "🔍 Checking InsightFace models..."
if [ ! -d "data/models/insightface/buffalo_l" ]; then
    echo "⚠️  InsightFace models not found"
    echo "   Models will be downloaded automatically on first run"
else
    echo "✅ InsightFace models found"
fi
echo ""

# Database setup (SQLite - automatic)
echo "💾 Database Setup (SQLite)..."
echo "   Database file: data/attendance.db"
echo "   ✅ No manual setup needed - SQLite creates automatically"
echo ""

# Check .env file
echo "⚙️  Checking configuration..."
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "   Please create .env file with required settings"
    exit 1
fi
echo "✅ Configuration file found"
echo ""

# Summary
echo "=============================================="
echo "✅ Setup Complete!"
echo "=============================================="
echo ""
echo "📋 System Configuration:"
echo "   • Python: 3.11"
echo "   • Database: SQLite (data/attendance.db)"
echo "   • Face Recognition: InsightFace (buffalo_l)"
echo "   • Anti-Spoofing: Lightweight ONNX (no TensorFlow)"
echo "   • Platform: M1 Mac ARM + Linux x86 compatible"
echo ""
echo "🚀 To start the server:"
echo "   source .venv311/bin/activate"
echo "   python main.py"
echo ""
echo "🌐 Server will run on: http://0.0.0.0:8000"
echo "   Access from browser: http://localhost:8000"
echo ""
echo "📖 Features:"
echo "   ✓ Real-time face recognition"
echo "   ✓ Anti-spoofing (detects photos/screens)"
echo "   ✓ Attendance tracking (IN/OUT)"
echo "   ✓ Excel export"
echo "   ✓ Multi-school support"
echo ""
