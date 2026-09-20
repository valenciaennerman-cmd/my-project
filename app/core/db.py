"""Database engine and session handling.

SQLite with WAL, one engine for the process. Sessions are short-lived and
created per unit of work; the repository owns all of them so no other module
has to think about transactions.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from ..models import tables as _tables  # noqa: F401  (imported for its side effect: registers the tables on SQLModel.metadata)

logger = logging.getLogger(__name__)


def build_engine(path: Path, echo: bool = False) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        echo=echo,
        # The watcher, the API and the price providers all touch the DB from
        # different tasks/threads; SQLite needs to be told that is fine.
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    logger.info("veritabani hazir: %s", path)
    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """A session that commits on success and rolls back on failure."""
    # expire_on_commit=False so returned rows stay readable after the
    # session closes -- there are no relationships to lazy-load.
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
