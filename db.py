"""
db.py — SQLite storage for the marathon training dashboard.

One table, one job: hold cleaned run records so the sync script can
insert new ones and the (future) API/dashboard can read from them.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "training.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    activity_id            TEXT PRIMARY KEY,
    date                    TEXT NOT NULL,          -- ISO date, e.g. 2026-07-15
    distance_km             REAL,
    duration_sec             INTEGER,
    avg_pace_sec_per_km       REAL,
    avg_hr                   INTEGER,
    max_hr                    INTEGER,
    elevation_gain_m          REAL,
    cadence_avg               REAL,
    training_load              REAL,
    resting_hr_that_day        INTEGER,
    sleep_hours_prior_night     REAL,
    perceived_type              TEXT,               -- easy / tempo / long / interval / race (tag manually later)
    synced_at                    TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(date);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_last_synced_date(conn: sqlite3.Connection) -> str | None:
    """Returns the most recent run date already in the DB, or None if empty."""
    row = conn.execute("SELECT MAX(date) AS max_date FROM runs").fetchone()
    return row["max_date"] if row and row["max_date"] else None


def insert_run(conn: sqlite3.Connection, record: dict) -> bool:
    """
    Insert a run record. Returns True if a new row was inserted,
    False if it already existed (duplicate activity_id).
    """
    columns = (
        "activity_id", "date", "distance_km", "duration_sec",
        "avg_pace_sec_per_km", "avg_hr", "max_hr", "elevation_gain_m",
        "cadence_avg", "training_load", "resting_hr_that_day",
        "sleep_hours_prior_night", "perceived_type",
    )
    placeholders = ", ".join(f":{c}" for c in columns)
    sql = f"""
        INSERT OR IGNORE INTO runs ({", ".join(columns)})
        VALUES ({placeholders})
    """
    cursor = conn.execute(sql, {c: record.get(c) for c in columns})
    return cursor.rowcount > 0


def get_all_runs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM runs ORDER BY date ASC").fetchall()
    return [dict(r) for r in rows]
