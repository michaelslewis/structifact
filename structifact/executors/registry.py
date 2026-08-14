from .duckdb import DuckDBExecutor

# Maps an --engine name to its Executor class (not an instance —
# each `structifact execute` invocation constructs its own, since
# an Executor holds real connection state that shouldn't be shared
# or reused across runs). Only one real implementation exists today;
# a future Postgres/Snowflake implementation (see docs/FUTURE_WORK.md's
# "Before a 1.0 Release" section) would be added here the same way.
EXECUTORS = {
    "duckdb": DuckDBExecutor,
}
