"""
Database connection and session management.

Provides SQLAlchemy engine, session factory, and dependency injection
for database sessions in FastAPI endpoints.
"""

from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

from .config import settings


# =============================================================================
# SQLAlchemy Base
# =============================================================================

Base = declarative_base()


# =============================================================================
# Engine Configuration
# =============================================================================

def get_engine_url() -> str:
    """
    Get database URL with proper async driver if needed.
    
    Returns:
        Database connection URL string
    """
    return settings.database_url


# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    get_engine_url(),
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    poolclass=QueuePool,
    pool_pre_ping=True,  # Enable connection health checks
    pool_recycle=settings.db_pool_recycle,   # Use config value (default 1800s)
    pool_timeout=settings.db_pool_timeout,   # Use config value (default 30s)
    echo=settings.debug,  # Log SQL queries in debug mode
)


# =============================================================================
# Session Factory
# =============================================================================

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


# =============================================================================
# Event Listeners for Connection Management
# =============================================================================

@event.listens_for(engine, "connect")
def set_connection_settings(dbapi_connection, connection_record):
    """
    Configure connection settings when a new connection is created.
    
    Sets timezone and statement timeout for safety.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("SET timezone='UTC'")
    cursor.execute("SET statement_timeout = '30s'")  # 30 second query timeout
    cursor.close()


@event.listens_for(engine, "checkout")
def ping_connection(dbapi_connection, connection_record, connection_proxy):
    """
    Verify connection is still valid when checked out from pool.
    
    This is a lightweight check complementing pool_pre_ping.
    """
    pass  # pool_pre_ping handles this, but hook is available for custom logic


# =============================================================================
# Dependency Injection
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database session injection.
    
    Creates a new session for each request and ensures proper cleanup.
    
    Yields:
        SQLAlchemy Session instance
        
    Example:
        @router.get("/leads")
        def get_leads(db: Session = Depends(get_db)):
            return db.query(Lead).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Database Utilities
# =============================================================================

def init_db() -> None:
    """
    Initialize database tables.
    
    Creates all tables defined in models. Should only be used
    in development or for initial setup. Production should use Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)


def check_db_connection() -> bool:
    """
    Check if database connection is healthy.

    Uses ``text()`` as required by SQLAlchemy 2.x — plain string SQL is
    deprecated and emits warnings in 1.4+ while failing in 2.0+.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
