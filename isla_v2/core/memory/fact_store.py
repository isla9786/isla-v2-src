import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from isla_v2.core.common.paths import FACTS_DB, ensure_dirs


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_expires_at(ttl_seconds: int | None) -> Optional[str]:
    if ttl_seconds is None:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()


def is_expired(expires_at: Optional[str]) -> bool:
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc)
    except ValueError:
        return False


def with_state(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["state"] = "expired" if is_expired(data.get("expires_at")) else "active"
    return data


def get_conn() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(FACTS_DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_fact_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS facts (
            namespace   TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            source      TEXT NOT NULL DEFAULT 'manual',
            updated_at  TEXT NOT NULL,
            expires_at  TEXT,
            PRIMARY KEY (namespace, key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fact_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace   TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT,
            source      TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            expires_at  TEXT,
            operation   TEXT NOT NULL
        )
        """
    )

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(facts)").fetchall()}
    if "expires_at" not in columns:
        conn.execute("ALTER TABLE facts ADD COLUMN expires_at TEXT")


def init_db() -> None:
    with get_conn() as conn:
        ensure_fact_schema(conn)
        conn.commit()


def record_history(
    conn: sqlite3.Connection,
    namespace: str,
    key: str,
    value: Optional[str],
    source: str,
    expires_at: Optional[str],
    operation: str,
) -> None:
    conn.execute(
        """
        INSERT INTO fact_history (namespace, key, value, source, updated_at, expires_at, operation)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (namespace, key, value, source, utc_now(), expires_at, operation),
    )


def set_fact(
    namespace: str,
    key: str,
    value: str,
    source: str = "manual",
    ttl_seconds: int | None = None,
) -> None:
    init_db()
    expires_at = compute_expires_at(ttl_seconds)
    updated_at = utc_now()
    with get_conn() as conn:
        ensure_fact_schema(conn)
        conn.execute(
            """
            INSERT INTO facts (namespace, key, value, source, updated_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace, key) DO UPDATE SET
                value = excluded.value,
                source = excluded.source,
                updated_at = excluded.updated_at,
                expires_at = excluded.expires_at
            """,
            (namespace, key, value, source, updated_at, expires_at),
        )
        record_history(conn, namespace, key, value, source, expires_at, "set")
        conn.commit()


def get_fact_record(namespace: str, key: str) -> Optional[dict]:
    init_db()
    with get_conn() as conn:
        ensure_fact_schema(conn)
        row = conn.execute(
            """
            SELECT namespace, key, value, source, updated_at, expires_at
            FROM facts
            WHERE namespace = ? AND key = ?
            """,
            (namespace, key),
        ).fetchone()
        return with_state(row) if row else None


def get_fact(namespace: str, key: str) -> Optional[str]:
    row = get_fact_record(namespace, key)
    return row["value"] if row else None


def list_facts(namespace: Optional[str] = None) -> list[dict]:
    init_db()
    with get_conn() as conn:
        ensure_fact_schema(conn)
        if namespace:
            rows = conn.execute(
                """
                SELECT namespace, key, value, source, updated_at, expires_at
                FROM facts
                WHERE namespace = ?
                ORDER BY key
                """,
                (namespace,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT namespace, key, value, source, updated_at, expires_at
                FROM facts
                ORDER BY namespace, key
                """
            ).fetchall()
        return [with_state(row) for row in rows]


def search_facts(query: str, namespace: Optional[str] = None, limit: int = 10) -> list[dict]:
    init_db()
    needle = f"%{query.strip()}%"
    with get_conn() as conn:
        ensure_fact_schema(conn)
        if namespace:
            rows = conn.execute(
                """
                SELECT namespace, key, value, source, updated_at, expires_at
                FROM facts
                WHERE namespace = ?
                  AND (namespace LIKE ? OR key LIKE ? OR value LIKE ?)
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (namespace, needle, needle, needle, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT namespace, key, value, source, updated_at, expires_at
                FROM facts
                WHERE namespace LIKE ? OR key LIKE ? OR value LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (needle, needle, needle, limit),
            ).fetchall()
        return [with_state(row) for row in rows]


def get_fact_history(namespace: str, key: str, limit: int = 10) -> list[dict]:
    init_db()
    with get_conn() as conn:
        ensure_fact_schema(conn)
        rows = conn.execute(
            """
            SELECT namespace, key, value, source, updated_at, expires_at, operation
            FROM fact_history
            WHERE namespace = ? AND key = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (namespace, key, limit),
        ).fetchall()
        return [with_state(row) for row in rows]


def delete_fact(namespace: str, key: str) -> bool:
    init_db()
    with get_conn() as conn:
        ensure_fact_schema(conn)
        row = conn.execute(
            """
            SELECT namespace, key, value, source, updated_at, expires_at
            FROM facts
            WHERE namespace = ? AND key = ?
            """,
            (namespace, key),
        ).fetchone()
        cur = conn.execute(
            "DELETE FROM facts WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
        if row:
            record_history(
                conn,
                row["namespace"],
                row["key"],
                row["value"],
                row["source"],
                row["expires_at"],
                "delete",
            )
        conn.commit()
        return cur.rowcount > 0


def cmd_init(_: argparse.Namespace) -> None:
    init_db()
    print(f"INIT_OK: {FACTS_DB}")


def cmd_set(args: argparse.Namespace) -> None:
    set_fact(args.namespace, args.key, args.value, args.source, ttl_seconds=args.ttl_seconds)
    print(f"SET_OK: {args.namespace}.{args.key}")


def cmd_get(args: argparse.Namespace) -> None:
    value = get_fact(args.namespace, args.key)
    if value is None:
        print("NOT_FOUND")
    else:
        print(value)


def cmd_list(args: argparse.Namespace) -> None:
    rows = list_facts(args.namespace)
    if not rows:
        print("EMPTY")
        return
    for row in rows:
        ttl_part = f" [expires_at={row['expires_at']}]" if row.get("expires_at") else ""
        print(
            f"{row['namespace']}.{row['key']} = {row['value']} "
            f"[source={row['source']}] [updated_at={row['updated_at']}] [state={row['state']}]"
            f"{ttl_part}"
        )


def cmd_search(args: argparse.Namespace) -> None:
    rows = search_facts(args.query, namespace=args.namespace, limit=args.limit)
    if not rows:
        print("EMPTY")
        return
    for row in rows:
        print(
            f"{row['namespace']}.{row['key']} = {row['value']} "
            f"[source={row['source']}] [state={row['state']}]"
        )


def cmd_history(args: argparse.Namespace) -> None:
    rows = get_fact_history(args.namespace, args.key, limit=args.limit)
    if not rows:
        print("EMPTY")
        return
    for row in rows:
        ttl_part = f" [expires_at={row['expires_at']}]" if row.get("expires_at") else ""
        print(
            f"{row['operation']} {row['namespace']}.{row['key']} = {row.get('value')} "
            f"[source={row['source']}] [updated_at={row['updated_at']}] [state={row['state']}]"
            f"{ttl_part}"
        )


def cmd_delete(args: argparse.Namespace) -> None:
    ok = delete_fact(args.namespace, args.key)
    print("DELETE_OK" if ok else "NOT_FOUND")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ISLA v2 trusted fact store")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.set_defaults(func=cmd_init)

    p_set = sub.add_parser("set")
    p_set.add_argument("namespace")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.add_argument("--source", default="manual")
    p_set.add_argument("--ttl-seconds", type=int, default=None)
    p_set.set_defaults(func=cmd_set)

    p_get = sub.add_parser("get")
    p_get.add_argument("namespace")
    p_get.add_argument("key")
    p_get.set_defaults(func=cmd_get)

    p_list = sub.add_parser("list")
    p_list.add_argument("namespace", nargs="?")
    p_list.set_defaults(func=cmd_list)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--namespace")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.set_defaults(func=cmd_search)

    p_history = sub.add_parser("history")
    p_history.add_argument("namespace")
    p_history.add_argument("key")
    p_history.add_argument("--limit", type=int, default=10)
    p_history.set_defaults(func=cmd_history)

    p_delete = sub.add_parser("delete")
    p_delete.add_argument("namespace")
    p_delete.add_argument("key")
    p_delete.set_defaults(func=cmd_delete)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
