from .base import Generator, Artifact
import yaml
from ..ir import TableSpec


class DBTYAMLGenerator(Generator):
    name = "dbt"

    def generate(self, table: TableSpec) -> Artifact:
        data = {
            "version": 2,
            "models": [
                {
                    "name": table.name,
                    "columns": [
                        {
                            "name": f.name,
                            "description": f.description or ""
                        }
                        for f in table.fields
                    ],
                }
            ],
        }

        return Artifact(
            filename=f"{table.name}.yml",
            content=yaml.dump(data, sort_keys=False)
        )