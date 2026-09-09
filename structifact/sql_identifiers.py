def quote_identifier(name: str) -> str:
    """
    Quote a SQL identifier (table/column name) for safe use in
    generated SQL text -- ANSI-standard double-quote syntax, verified
    correct for both engines Structifact executes against today,
    DuckDB and PostgreSQL (see docs/DECISION_HISTORY.md's Issue #1
    investigation: both use identical quoted-identifier syntax, unlike
    e.g. MySQL's backticks or SQL Server's brackets, neither of which
    Structifact supports). An embedded double quote is escaped by
    doubling it, the same ANSI rule both engines follow.

    Always quotes, even when the identifier would already be safe
    bare (e.g. "mandt" -> '"mandt"') -- deliberately not a "quote only
    if needed" heuristic. That would require maintaining a
    reserved-word list across two engines for no real benefit:
    quoting an already-safe identifier is a semantic no-op in both
    (an unquoted lowercase identifier and its quoted form resolve to
    the same relation/column), so one unconditional rule is simpler
    and can't drift out of sync with either engine's keyword list.

    Used only where a plain identifier is being emitted -- a table or
    column name. Never applied to expression/on/filter/
    check.expression anywhere in this codebase: those are raw,
    trusted SQL text Structifact deliberately never parses (see
    ir.py), and an identifier referenced inside one of them is the
    metadata author's own literal text, which this function does not
    touch.
    """
    return '"' + name.replace('"', '""') + '"'
