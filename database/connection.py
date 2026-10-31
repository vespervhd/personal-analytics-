"""SQLAlchemy engine and session handling (SQLite).

The engine is created once per process and cached. Repository functions
take an explicit session — there is no hidden global session — so callers
control transactions.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import SETTINGS
from utils.logger import get_logger

log = get_logger("database_connection")

_engine = None
_SessionFactory: sessionmaker | None = None


def get_engine():
    """Return the cached SQLite engine for ``SETTINGS.db_url``."""
    global _engine, _SessionFactory
    if _engine is None:
        SETTINGS.ensure_directories()
        _engine = create_engine(
            SETTINGS.db_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        _SessionFactory = sessionmaker(bind=_engine, future=True)
        log.info("Database engine created for {}", SETTINGS.db_path)
    return _engine


def init_db() -> None:
    """Create all tables (no-op when they already exist)."""
    from database.models import Base

    engine = get_engine()
    Base.metadata.create_all(engine)
    log.info("Database tables ensured at {}", SETTINGS.db_path)


def get_session() -> Session:
    """Return a new session (caller owns closing it)."""
    get_engine()
    assert _SessionFactory is not None
    return _SessionFactory()
