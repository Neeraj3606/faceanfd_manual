#!/usr/bin/env python3
"""
Local development startup script with pre-flight environment and database checks.
Not used in Docker/Render deployments — the production entry point is main.py via uvicorn directly.
"""

import os
import socket
import sys
import subprocess
from dotenv import load_dotenv

load_dotenv()


def check_env() -> bool:
    """Validate required environment variables before starting."""
    db_url = os.getenv("DATABASE_URL")
    secret_key = os.getenv("SECRET_KEY")

    if not db_url:
        print("DATABASE_URL is not set. Provide a PostgreSQL connection string in .env.")
        return False

    weak_keys = {
        "your-secret-key-here-change-in-production",
        "change-this-secret-key-in-production",
        "your-super-secret-key-here",
    }
    if not secret_key or secret_key.strip() in weak_keys or len(secret_key.strip()) < 32:
        print(
            "SECRET_KEY is missing or too short (minimum 32 characters).\n"
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "Then add it to your .env file."
        )
        return False

    print("Environment variables verified.")
    return True


def test_database_connection() -> bool:
    """Attempt a lightweight connection to the configured database."""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import OperationalError

        db_url = os.getenv("DATABASE_URL")
        engine = create_engine(db_url, pool_pre_ping=True)

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        print("Database connection successful.")
        return True

    except Exception as exc:
        print(f"Database connection failed: {exc}")
        print("Verify DATABASE_URL in .env and ensure the database server is reachable.")
        return False


def is_port_available(host: str, port: int) -> bool:
    """Return True if the given host/port can be bound."""
    probe_host = "127.0.0.1" if host == "0.0.0.0" else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((probe_host, port))
        except OSError:
            return False
    return True


def resolve_server_port(host: str, preferred_port: int, search_limit: int = 20) -> int:
    """Return the requested port if available, otherwise find the next free port."""
    if is_port_available(host, preferred_port):
        return preferred_port

    for port in range(preferred_port + 1, preferred_port + search_limit + 1):
        if is_port_available(host, port):
            print(f"Port {preferred_port} is in use. Using port {port} instead.")
            return port

    raise RuntimeError(
        f"No free port found between {preferred_port} and {preferred_port + search_limit}."
    )


def start_server() -> None:
    """Launch the Uvicorn ASGI server."""
    host = os.getenv("HOST", "0.0.0.0")
    port = resolve_server_port(host, int(os.getenv("PORT", "8000")))
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host

    print(f"Starting server on http://{host}:{port}")
    print(f"Local access: http://{browser_host}:{port}")

    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", str(port),
    ])


def main() -> None:
    print("Face Attendance — Local Startup Check\n" + "-" * 40)

    if not check_env():
        sys.exit(1)

    if not test_database_connection():
        response = input("\nDatabase connection failed. Start anyway? (y/N): ")
        if response.strip().lower() != "y":
            sys.exit(1)

    start_server()


if __name__ == "__main__":
    main()
