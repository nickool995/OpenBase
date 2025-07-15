
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "benchmark_results.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    codebase1 TEXT,
    codebase2 TEXT,
    total1 REAL,
    total2 REAL,
    details_json TEXT
);
"""


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_CREATE_SQL)
    return conn


def record_run(codebase1: str, codebase2: str, total1: float, total2: float, details: dict):
    """Inserts a new run record into the database.

    Args:
        codebase1 (str): The first codebase name.
        codebase2 (str): The second codebase name.
        total1 (float): The total for the first codebase.
        total2 (float): The total for the second codebase.
        details (dict): A dictionary of additional details.
    """
    conn = _get_conn()
    conn.execute(
        "INSERT INTO runs (timestamp, codebase1, codebase2, total1, total2, details_json) VALUES (?,?,?,?,?,?)",
        (datetime.utcnow().isoformat(), codebase1, codebase2, total1, total2, json.dumps(details)),
    )
    conn.commit()
    conn.close()


def get_recent_runs(limit: int = 20):
    """Retrieves the most recent runs from the database.

    Args:
        limit (int): The number of recent runs to retrieve. Defaults to 20.

    Returns:
        list: A list of rows from the database.
    """
    conn = _get_conn()
    cur = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows 
