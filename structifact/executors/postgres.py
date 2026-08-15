from typing import Any, Dict, List

from .base import Executor


class PostgresExecutor(Executor):
    """
    Executes generated DDL against a real PostgreSQL server via
    psycopg2. Phase 8A — the second real Executor implementation,
    proving the interface DuckDB validated also holds for a
    credentialed, networked engine.

    Persistence contract (see base.py's docstring for the full
    Phase 8A note): connects with autocommit enabled, so every
    operation is immediately durable — matching DuckDBExecutor's
    existing effective behavior. This is deliberate compatibility
    behavior, not real transaction management; explicit transactions,
    rollback, connection pooling, and retry logic are Phase 8C.

    `connection_args["connection"]` is a PostgreSQL DSN (e.g.
    "postgresql://user:pass@host:port/dbname"), passed straight to
    psycopg2 — Structifact never parses or constructs it. Unlike
    DuckDB, there is no sensible default; a missing connection string
    is a configuration error, not an in-memory fallback.
    """

    name = "postgres"

    def __init__(self) -> None:
        self._conn = None

    def connect(self, **connection_args: Any) -> None:
        import psycopg2  # lazy import: only required if this executor runs

        dsn = connection_args.get("connection")
        if not dsn:
            raise ValueError(
                "postgres executor requires a --connection DSN "
                "(e.g. postgresql://user:pass@host:port/dbname)"
            )

        self._conn = psycopg2.connect(dsn=dsn)
        self._conn.autocommit = True

    def execute_ddl(self, sql: str) -> None:
        self._require_connection()
        with self._conn.cursor() as cur:
            cur.execute(sql)

    def load_rows(self, table_name: str, columns: List[str], rows: List[Dict[str, Any]]) -> None:
        self._require_connection()

        if not rows:
            return

        column_list = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"

        values = [[row.get(col) for col in columns] for row in rows]
        with self._conn.cursor() as cur:
            cur.executemany(insert_sql, values)

    def query(self, sql: str) -> List[Dict[str, Any]]:
        self._require_connection()

        with self._conn.cursor() as cur:
            cur.execute(sql)
            column_names = [d[0] for d in cur.description]
            return [dict(zip(column_names, row)) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _require_connection(self) -> None:
        if self._conn is None:
            raise RuntimeError(
                f"{self.name} executor is not connected — call connect() first"
            )
