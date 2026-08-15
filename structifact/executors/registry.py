from .duckdb import DuckDBExecutor
from .postgres import PostgresExecutor

# Maps an --engine name to its Executor class (not an instance —
# each `structifact execute` invocation constructs its own, since
# an Executor holds real connection state that shouldn't be shared
# or reused across runs). Importing these modules is safe even
# without duckdb/psycopg2 installed — each executor imports its
# third-party driver lazily, inside connect(), not at module load
# time (see duckdb.py/postgres.py). A future Snowflake implementation
# (see docs/FUTURE_WORK.md's "Before a 1.0 Release" section) would be
# added here the same way.
EXECUTORS = {
    "duckdb": DuckDBExecutor,
    "postgres": PostgresExecutor,
}
