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

        raw_accepted_values = field.get("accepted_values")
        accepted_values = (
            [str(v) for v in raw_accepted_values]
            if raw_accepted_values is not None
            else None
        )

        raw_depends_on = field.get("depends_on")
        depends_on = (
            [str(v) for v in raw_depends_on]
            if raw_depends_on is not None
            else None
        )

        fields.append(
            FieldSpec(
                name=field["name"],
                type=parsed["type"],
                raw_type=field["type"],
                description=field.get("description"),
                role=field.get("role"),
                accepted_values=accepted_values,

                length=parsed.get("length"),
                precision=parsed.get("precision"),
                scale=parsed.get("scale"),

                nullable=field.get("nullable", True),

                computed=field.get("computed", False),
                expression=field.get("expression"),
                depends_on=depends_on,
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
