import yaml

from ..ir import TableSpec, FieldSpec


def load_yaml(path: str) -> TableSpec:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    fields = [
        FieldSpec(
            name=field["name"],
            type=field["type"],
            description=field.get("description"),
        )
        for field in data["fields"]
    ]

    return TableSpec(
        name=data["table"],
        fields=fields,
    )