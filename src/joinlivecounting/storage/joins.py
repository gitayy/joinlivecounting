import time

from .db import connect


def _count_since(conn, thread_id: str, cutoff: float) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM joins WHERE thread_id = ? AND joined_at > ?",
        (thread_id, cutoff),
    ).fetchone()
    return row[0]


def first_exceeded(thread_id: str, limits) -> object | None:
    if not limits:
        return None
    now = time.time()
    conn = connect()
    try:
        for limit in limits:
            if _count_since(conn, thread_id, now - limit.seconds) >= limit.max:
                return limit
    finally:
        conn.close()
    return None

def claim(thread_id: str, username: str, limits) -> object | None:
    now = time.time()
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for limit in limits:
            if _count_since(conn, thread_id, now - limit.seconds) >= limit.max:
                conn.execute("ROLLBACK")
                return limit
        conn.execute(
            "INSERT INTO joins (thread_id, username, joined_at) VALUES (?, ?, ?)",
            (thread_id, username, now),
        )
        conn.execute("COMMIT")
        return None
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

def release(thread_id: str, username: str) -> None:
    conn = connect()
    try:
        conn.execute(
            "DELETE FROM joins WHERE id = ("
            "  SELECT id FROM joins WHERE thread_id = ? AND username = ?"
            "  ORDER BY joined_at DESC LIMIT 1"
            ")",
            (thread_id, username),
        )
    finally:
        conn.close()

def recent(thread_id: str, seconds: int, limit: int = 50):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT username, joined_at FROM joins"
            " WHERE thread_id = ? AND joined_at > ?"
            " ORDER BY joined_at DESC LIMIT ?",
            (thread_id, time.time() - seconds, limit),
        ).fetchall()
        return [{"username": u, "joined_at": t} for u, t in rows]
    finally:
        conn.close()

def joins_since(thread_id: str, since: float) -> int:
    conn = connect()
    try:
        return _count_since(conn, thread_id, since)
    finally:
        conn.close()
