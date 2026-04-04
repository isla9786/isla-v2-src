import sqlite3
from datetime import datetime, timezone
from typing import Optional

from isla_v2.core.common.paths import NOTES_DB, ensure_dirs


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(NOTES_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace   TEXT NOT NULL,
                body        TEXT NOT NULL,
                kind        TEXT NOT NULL DEFAULT 'note',
                source      TEXT NOT NULL DEFAULT 'manual',
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.commit()


def add_note(namespace: str, body: str, source: str = "manual", kind: str = "note") -> int:
    init_db()
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO notes (namespace, body, kind, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (namespace, body, kind, source, utc_now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def recent_notes(namespace: Optional[str] = None, limit: int = 10) -> list[dict]:
    init_db()
    with get_conn() as conn:
        if namespace:
            rows = conn.execute(
                """
                SELECT id, namespace, body, kind, source, created_at
                FROM notes
                WHERE namespace = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (namespace, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, namespace, body, kind, source, created_at
                FROM notes
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def search_notes(query: str, namespace: Optional[str] = None, limit: int = 10) -> list[dict]:
    init_db()
    needle = f"%{query.strip()}%"
    with get_conn() as conn:
        if namespace:
            rows = conn.execute(
                """
                SELECT id, namespace, body, kind, source, created_at
                FROM notes
                WHERE namespace = ?
                  AND (namespace LIKE ? OR body LIKE ? OR kind LIKE ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (namespace, needle, needle, needle, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, namespace, body, kind, source, created_at
                FROM notes
                WHERE namespace LIKE ? OR body LIKE ? OR kind LIKE ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (needle, needle, needle, limit),
            ).fetchall()
        return [dict(row) for row in rows]
