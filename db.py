"""
db.py — SQLite connection helper and schema initialiser.
Uses stdlib sqlite3 only — no ORM, no SQLAlchemy.
Parameterized queries (? placeholders) are enforced throughout the codebase.
"""
import sqlite3
import os
from pathlib import Path

import config


def get_db() -> sqlite3.Connection:
    """
    Open and return a sqlite3 connection to the configured database.
    Row factory is set to sqlite3.Row so columns are accessible by name.
    """
    db_path = config.DATABASE_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safer concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """
    Run schema.sql against the database.  Uses CREATE TABLE IF NOT EXISTS,
    so it is safe to call on every startup.
    """
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    conn = get_db()
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
