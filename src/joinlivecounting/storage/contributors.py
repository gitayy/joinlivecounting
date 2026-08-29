import time

from .db import connect


def baseline(thread_id: str) -> tuple[int, float] | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT count, scanned_at FROM contributor_counts WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return (row[0], row[1])
    finally:
        conn.close()

def set_baseline(thread_id: str, count: int, scanned_at: float) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO contributor_counts (thread_id, count, scanned_at)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(thread_id) DO UPDATE SET count = excluded.count,"
            " scanned_at = excluded.scanned_at",
            (thread_id, count, scanned_at),
        )
    finally:
        conn.close()

def claim_scan(thread_id: str, max_age: float) -> float | None:
    now = time.time()
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT scanned_at FROM contributor_counts WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        if row is not None and now - row[0] < max_age:
            conn.execute("ROLLBACK")
            return None
        previous = row[0] if row else None
        conn.execute(
            "INSERT INTO contributor_counts (thread_id, count, scanned_at)"
            " VALUES (?, NULL, ?)"
            " ON CONFLICT(thread_id) DO UPDATE SET scanned_at = excluded.scanned_at",
            (thread_id, now),
        )
        conn.execute("COMMIT")
        return previous if previous is not None else 0.0
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

def restore_scan_time(thread_id: str, scanned_at: float) -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE contributor_counts SET scanned_at = ? WHERE thread_id = ?",
            (scanned_at, thread_id),
        )
    finally:
        conn.close()

def set_blocked(thread_id: str, usernames) -> int:
    now = time.time()
    rows = [(thread_id, name.casefold(), now) for name in usernames]
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM blocked WHERE thread_id = ?", (thread_id,))
        conn.executemany(
            "INSERT INTO blocked (thread_id, username, seen_at) VALUES (?, ?, ?)", rows
        )
        conn.execute("COMMIT")
        return len(rows)
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

def is_blocked(thread_id: str, username: str) -> bool:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM blocked WHERE thread_id = ? AND username = ?",
            (thread_id, username.casefold()),
        ).fetchone()
        return row is not None
    finally:
        conn.close()

def blocked_count(thread_id: str) -> int:
    conn = connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM blocked WHERE thread_id = ?", (thread_id,)
        ).fetchone()[0]
    finally:
        conn.close()
