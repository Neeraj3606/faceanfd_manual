#!/usr/bin/env python3
"""
Production server startup script with checks
"""

import os
import socket
import sys
import subprocess
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_env():
    """Check required environment variables"""
    print("🔍 Checking environment variables...")
    
    db_url = os.getenv("DATABASE_URL")
    secret_key = os.getenv("SECRET_KEY")
    
    if not db_url:
        db_url = "sqlite:///data/attendance.db"
        os.environ["DATABASE_URL"] = db_url
        print("✅ DATABASE_URL not set, defaulting to SQLite: sqlite:///data/attendance.db")
    
    if (
        not secret_key
        or secret_key.strip() in {
            "your-secret-key-here-change-in-production",
            "change-this-secret-key-in-production",
            "your-super-secret-key-here",
        }
        or len(secret_key.strip()) < 32
    ):
        print("❌ SECRET_KEY is missing or insecure!")
        print("   Run: python generate_secret.py")
        print("   Then update .env file\n")
        return False
    else:
        print("✅ SECRET_KEY is set")
    
    if not db_url.lower().startswith("sqlite"):
        print("❌ Only SQLite is supported.")
        print("   Set DATABASE_URL=sqlite:///data/attendance.db")
        return False
    print("✅ SQLite database configured")
    
    return True

def test_database_connection():
    """Test database connection"""
    print("\n🔍 Testing database connection...")
    
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import OperationalError
        
        db_url = os.getenv("DATABASE_URL")
        engine = create_engine(db_url, pool_pre_ping=True)
        
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        print("✅ Database connection successful!")
        return True
        
    except OperationalError as e:
        print(f"❌ Database connection failed!")
        print(f"   Error: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Verify DATABASE_URL in .env")
        print("   2. Ensure data/ directory is writable")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def create_tables():
    """Create database tables"""
    print("\n🔍 Creating database tables...")
    
    try:
        from app.db import engine, Base
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created/verified successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to create tables: {e}")
        return False

def is_port_available(host: str, port: int) -> bool:
    """Check whether a TCP port is free for the requested host."""
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((probe_host, port))
        except OSError:
            return False
    return True

def resolve_server_port(host: str, preferred_port: int, search_limit: int = 20) -> int:
    """Return the requested port when free, otherwise the next available port."""
    if is_port_available(host, preferred_port):
        return preferred_port

    for port in range(preferred_port + 1, preferred_port + search_limit + 1):
        if is_port_available(host, port):
            print(f"⚠️ Port {preferred_port} busy hai, server port {port} par start hoga.")
            return port

    raise RuntimeError(
        f"No free port found between {preferred_port} and {preferred_port + search_limit}."
    )

def start_server():
    """Start the uvicorn server"""
    print("\n🚀 Starting server...")
    print("=" * 50)
    
    host = os.getenv("HOST", "0.0.0.0")
    port = resolve_server_port(host, int(os.getenv("PORT", "8000")))
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    
    print(f"📡 Server will run on: http://{host}:{port}")
    print(f"🔗 Frontend URL: http://{browser_host}:{port}/static/login.html")
    print("=" * 50 + "\n")
    
    # Start server
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", str(port),
        "--reload", "false"
    ])

def main():
    """Main function"""
    print("=" * 50)
    print("🎓 Face Attendance - Production Startup")
    print("=" * 50 + "\n")
    
    # Check environment
    if not check_env():
        sys.exit(1)
    
    # Test database
    if not test_database_connection():
        response = input("\n⚠️  Database not connected. Start anyway? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # Create tables
    if not create_tables():
        print("⚠️  Continuing despite table creation issues...")
    
    # Start server
    start_server()

if __name__ == "__main__":
    main()
