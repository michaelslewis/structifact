import yaml

from ..ir import DatasetSpec, FieldSpec, ConstraintSpec
from ..types import parse_type


def load_yaml(path: str) -> DatasetSpec:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if "dataset" in data:
        dataset = data["dataset"]

        name = dataset["name"]
        description = dataset.get("description")
    else:
        name = data["table"]
        description = None

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

    constraints = [
        ConstraintSpec(
            type=constraint["type"],
            columns=constraint["columns"],
        )
        for constraint in data.get("constraints", [])
    ]

    return DatasetSpec(
        name=name,
        description=description,
        fields=fields,
        constraints=constraints,
    )