from .base import Generator, Artifact
from ..ir import TableSpec


class SQLGenerator(Generator):
    name = "sql"

    def generate(self, table: TableSpec) -> Artifact:
        columns = []
        for f in table.fields:
            columns.append(f"    {f.name} TEXT")

        sql = f"""CREATE TABLE {table.name} (
{',\n'.join(columns)}
);"""

        return Artifact(
            filename=f"{table.name}.sql",
            content=sql
        )