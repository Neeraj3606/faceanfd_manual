"""
Database setup (SQLAlchemy)

✔ Supports PostgreSQL (Render) and SQLite (local dev)
✔ Creates tables automatically (main.py lifespan)
✔ Provides session to FastAPI
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import DB_URL

# --------------------------------
# Fix Render's legacy postgres:// URL prefix
# SQLAlchemy 1.4+ requires postgresql://
# --------------------------------
_db_url = DB_URL
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)

# --------------------------------
# Engine
# --------------------------------
connect_args = {}

if _db_url.startswith("sqlite"):
    # SQLite: fix thread issue for FastAPI
    connect_args = {"check_same_thread": False}
    engine = create_engine(
        _db_url,
        pool_pre_ping=True,
        connect_args=connect_args,
        echo=False,
    )
else:
    # PostgreSQL (Render): use connection pooling
    engine = create_engine(
        _db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=300,  # recycle connections every 5 minutes
        echo=False,
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