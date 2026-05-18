"""
Database setup (SQLAlchemy)

✔ Uses SQLite database
✔ Creates tables automatically (main.py lifespan)
✔ Provides session to FastAPI
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DB_URL


# --------------------------------
# Engine (SQLite)
# --------------------------------
connect_args = {}

# ✅ SQLite thread fix for FastAPI
if DB_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
    echo=False  # Set to True for SQL logging
)


# --------------------------------
# Session
# --------------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# --------------------------------
# Base class for models
# --------------------------------
Base = declarative_base()


# --------------------------------
# Dependency (FastAPI will use this)
# --------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()