import yaml

from ..ir import TableSpec


def generate_dbt_yaml(table: TableSpec) -> str:
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

    return yaml.dump(data, sort_keys=False)