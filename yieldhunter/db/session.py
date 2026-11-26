"""Lazy database engine and session management.

Unlike the legacy ``db/client.py``, importing this module does **not** require
``DATABASE_URL`` to be set: the engine is created lazily on first database use,
and tests can inject an isolated engine via ``configure_session(engine)``.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        load_dotenv()
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL environment variable is not set")
        _engine = create_engine(db_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory


def get_session() -> OrmSession:
    return get_session_factory()()


@contextmanager
def session_scope() -> Iterator[OrmSession]:
    """Open a DB session and guarantee it is closed on exit."""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def configure_session(engine: Engine) -> sessionmaker:
    """Bind the package's session factory to *engine* (used by tests)."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = sessionmaker(bind=engine)
    return _session_factory


def reset_session() -> None:
    """Clear cached engine/session factory so the next call re-reads ``DATABASE_URL``."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
