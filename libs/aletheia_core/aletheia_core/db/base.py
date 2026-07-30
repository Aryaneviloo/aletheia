"""
aletheia_core.db.base
======================
Two ways to get a session, because there are two kinds of caller:
  - FastAPI routes use `get_db()`, a generator dependency FastAPI's
    `Depends()` knows how to open/close automatically per request.
  - Celery tasks use `session_scope()`, a plain context manager — tasks
    aren't FastAPI routes and have no dependency-injection system to
    hand them a session, so they open and close their own explicitly.

"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from aletheia_core.config import get_settings


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_settings = get_settings()

engine = create_engine(
    str(_settings.database_url),
    pool_size=_settings.database_pool_size,
    max_overflow=_settings.database_pool_max_overflow,
    pool_pre_ping=True,   
    echo=(_settings.log_level == "DEBUG"),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)



def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Context manager for Celery tasks that needs a database session.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()