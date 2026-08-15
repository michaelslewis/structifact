from typing import Any, Dict, List

from .base import Executor


class DuckDBExecutor(Executor):
    """
    Executes generated DDL against a local DuckDB file (or an
    in-memory database, if `connection` is omitted). No credentials,
    no network, no server — the first real Executor implementation
    specifically because it needs none of those, letting the
    Executor interface itself get proven before a credentialed
    engine (Postgres, Snowflake — see docs/FUTURE_WORK.md) is
    attempted.
    """

    name = "duckdb"

    def __init__(self) -> None:
        self._conn = None

    def connect(self, **connection_args: Any) -> None:
        import duckdb  # lazy import: only required if this executor runs

        database = connection_args.get("connection") or ":memory:"
        self._conn = duckdb.connect(database=database)

    def execute_ddl(self, sql: str) -> None:
        self._require_connection()
        self._conn.execute(sql)

    def load_rows(self, table_name: str, columns: List[str], rows: List[Dict[str, Any]]) -> None:
        self._require_connection()

        if not rows:
            return

        column_list = ", ".join(columns)
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"

        values = [[row.get(col) for col in columns] for row in rows]
        self._conn.executemany(insert_sql, values)

    def query(self, sql: str) -> List[Dict[str, Any]]:
        self._require_connection()

        cursor = self._conn.execute(sql)
        column_names = [d[0] for d in cursor.description]

        return [dict(zip(column_names, row)) for row in cursor.fetchall()]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _require_connection(self) -> None:
        if self._conn is None:
            raise RuntimeError(
                f"{self.name} executor is not connected — call connect() first"
            )
