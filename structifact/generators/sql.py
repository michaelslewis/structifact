from .base import Generator, Artifact
from ..ir import DatasetSpec


class SQLGenerator(Generator):
    name = "sql"

    def generate(self, table: DatasetSpec) -> Artifact:
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