import json
import os
import sqlite3
import threading
import time

from . import config

_lock = threading.Lock()


def _connect():
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                package TEXT NOT NULL,
                issue_numbers TEXT NOT NULL,
                advisories TEXT NOT NULL,
                session_id TEXT,
                status TEXT NOT NULL,
                pr_url TEXT,
                acu_consumed REAL,
                dry_run INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_dict(row):
    return {
        "id": row["id"],
        "package": row["package"],
        "issue_numbers": json.loads(row["issue_numbers"]),
        "advisories": json.loads(row["advisories"]),
        "session_id": row["session_id"],
        "status": row["status"],
        "pr_url": row["pr_url"],
        "acu_consumed": row["acu_consumed"],
        "dry_run": bool(row["dry_run"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def record_run(package, issue_numbers, advisories, session_id, status, dry_run):
    now = time.time()
    with _lock, _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO runs (package, issue_numbers, advisories, session_id, status,
                               pr_url, acu_consumed, dry_run, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
            """,
            (
                package,
                json.dumps(issue_numbers),
                json.dumps(advisories),
                session_id,
                status,
                int(dry_run),
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row)


def update_run(run_id, status=None, pr_url=None, acu_consumed=None):
    fields, values = [], []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if pr_url is not None:
        fields.append("pr_url = ?")
        values.append(pr_url)
    if acu_consumed is not None:
        fields.append("acu_consumed = ?")
        values.append(acu_consumed)
    fields.append("updated_at = ?")
    values.append(time.time())
    values.append(run_id)
    with _lock, _connect() as conn:
        conn.execute(f"UPDATE runs SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()


def all_runs():
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]


def running_runs():
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM runs WHERE status = 'running'").fetchall()
        return [_row_to_dict(r) for r in rows]


def dispatched_packages():
    """Packages that already have a non-skipped run on file, so we never
    dispatch the same package twice."""
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT DISTINCT package FROM runs").fetchall()
        return {r["package"] for r in rows}


def clear_runs():
    """Wipe the run ledger - used by the dashboard's Reset button so a demo
    can be re-run from a clean slate."""
    with _lock, _connect() as conn:
        deleted = conn.execute("DELETE FROM runs").rowcount
        conn.commit()
        return deleted


def summary():
    runs = all_runs()
    counts = {}
    for r in runs:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    total_acu = sum(r["acu_consumed"] or 0 for r in runs)
    return {
        "total_runs": len(runs),
        "by_status": counts,
        "total_acu_consumed": total_acu,
    }
