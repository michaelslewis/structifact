from .base import Generator, Artifact
from ..ir import DatasetSpec


SQL_TYPE_MAP = {
    "string": "TEXT",
    "integer": "INTEGER",
    "decimal": "DECIMAL",
    "timestamp": "TIMESTAMP",
    "date": "DATE",
    "boolean": "BOOLEAN",
}


def _sql_type(f) -> str:
    if f.type == "decimal" and f.precision is not None and f.scale is not None:
        return f"DECIMAL({f.precision},{f.scale})"

    return SQL_TYPE_MAP.get(f.type, "TEXT")


class SQLGenerator(Generator):
    name = "sql"

    def generate(self, table: DatasetSpec) -> Artifact:
        columns = []
        for f in table.fields:
            columns.append(f"    {f.name} {_sql_type(f)}")

        joined_columns = ',\n'.join(columns)

        sql = f"""CREATE TABLE {table.name} (
{joined_columns}
);"""

        return Artifact(
            filename=f"{table.name}.sql",
            content=sql
        )