import yaml
from .ir import DatasetSpec, FieldSpec


def load_metadata(path: str) -> DatasetSpec:
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

    return DatasetSpec(
        name=data["table"],
        fields=fields,
    )