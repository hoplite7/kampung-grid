"""Database connection. SQLite keeps everything in one file: backend/kampung.db."""

import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

DB_PATH = Path(os.getenv("KG_DB_PATH", Path(__file__).resolve().parent.parent / "kampung.db"))
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def create_tables() -> bool:
    """Create any missing tables. Returns True if the database had to be rebuilt.

    If an existing table is missing columns (because the code was updated, e.g. Week 1
    -> Week 2), the old demo data can't be used, so every table is rebuilt empty and
    the caller reloads the seed data. Demo data is fictional, so nothing real is lost.
    """
    from sqlalchemy import inspect

    from . import models  # noqa: F401  (registers the tables)

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    outdated = any(
        table.name in existing
        and not {c.name for c in table.columns} <= {c["name"] for c in inspector.get_columns(table.name)}
        for table in SQLModel.metadata.sorted_tables
    )
    if outdated:
        print("[db] Database is from an older version: rebuilding it with fresh demo data")
        reset_tables()
        return True
    SQLModel.metadata.create_all(engine)
    return False


def reset_tables() -> None:
    """Drop every table and create them again, empty."""
    from . import models  # noqa: F401

    SQLModel.metadata.drop_all(engine)
    # SQLite keeps deleted data in the file until it is "vacuumed". Vacuum, so no
    # old plain-text data (e.g. from before profiles were encrypted) lingers on disk.
    with engine.connect() as conn:
        conn.exec_driver_sql("VACUUM")
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
