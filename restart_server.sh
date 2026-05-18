#!/bin/bash

echo "🛑 Stopping server..."
pkill -f "python.*main.py"
sleep 2

echo "🧹 Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

echo "✅ Starting server..."
python main.py
