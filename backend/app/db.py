"""SQLAlchemy engine + session factory (synchronous; only Sarvam calls are async).

Only used when DATABASE_URL is set. Without it the app runs on the in-memory corpus (see app/local_store.py).
"""
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# connect_timeout: without it, an unreachable DB can hang for minutes on Windows.
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True,
                       connect_args={"connect_timeout": 5}) if settings.use_db else None
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    if engine is None:
        raise RuntimeError("DATABASE_URL is not set")
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session() -> Iterator[Session | None]:
    """FastAPI dependency. Yields None when running without a database."""
    if engine is None:
        yield None
        return
    with session_scope() as s:
        yield s


def db_ok() -> bool:
    if engine is None:
        return False
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
