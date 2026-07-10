import yaml

from ..ir import TableSpec, FieldSpec
from ..types import parse_type


def load_yaml(path: str) -> TableSpec:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    fields = []

    for field in data["fields"]:
        parsed = parse_type(field["type"])

        fields.append(
            FieldSpec(
                name=field["name"],
                type=parsed["type"],
                raw_type=field["type"],
                description=field.get("description"),

                length=parsed.get("length"),
                precision=parsed.get("precision"),
                scale=parsed.get("scale"),
            )
        )

    return TableSpec(
        name=data["table"],
        fields=fields,
    )