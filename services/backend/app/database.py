"""
Database configuration and session management.

This module sets up SQLAlchemy engine, session factory, and base model.
All database credentials are loaded from environment variables via Settings.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Create database engine using settings
# Connection pooling is configured for optimal performance
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,  # Number of connections to maintain in pool
    max_overflow=30,  # Maximum overflow connections
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,  # Recycle connections after 1 hour
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
