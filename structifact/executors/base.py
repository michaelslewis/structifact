from typing import Any, Dict, List


class Executor:
    """
    Base class for all Structifact executors (Phase 8 — Execution and
    Platform Integrations).

    An Executor runs generated SQL against a real database engine —
    a genuinely different responsibility from a Generator, which
    only ever produces text. Where SQLGenerator answers "what SQL
    should exist for this dataset," an Executor answers "does that
    SQL actually work against a real engine."

    v1 scope, deliberately minimal (see docs/FUTURE_WORK.md's
    "Before a 1.0 Release" section for what's intentionally NOT
    here yet): a single connect/run/close per invocation, no
    transaction management, no connection pooling, no retry logic.
    Only DDL execution is supported — running a computed field's
    ModelGenerator SELECT against real data is a distinct, future
    capability, not this one. This mirrors SQLGenerator's own
    documented boundary (its docstring explicitly scopes itself to
    schema declaration, not transformation execution).

    connection_args are passed to connect(), never to __init__ or
    stored anywhere persistent — same bring-your-own-credentials
    posture as structifact/llm.py's ANTHROPIC_API_KEY handling.
    Every engine-specific implementation defines what connection_args
    it actually needs (DuckDB: just `database`, a file path or
    omitted for in-memory; a future Postgres/Snowflake implementation
    would need host/user/password/etc.) — the interface itself stays
    generic.
    """

    name: str

    def connect(self, **connection_args: Any) -> None:
        raise NotImplementedError

    def execute_ddl(self, sql: str) -> None:
        raise NotImplementedError

    def load_rows(self, table_name: str, columns: List[str], rows: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def query(self, sql: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
