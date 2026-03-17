"""
Core module for NeuroReach AI backend.

Contains configuration, database setup, and security utilities.
"""

from .config import settings
from .database import get_db, engine, SessionLocal

__all__ = ["settings", "get_db", "engine", "SessionLocal"]
