from decimal import Decimal

import yaml

from ..ir import DatasetSpec, FieldSpec, ConstraintSpec
from ..types import parse_type


def _parse_bound(raw):
    """
    Converts a YAML-parsed numeric literal (already a Python int or
    float by the time PyYAML hands it to us) into a Decimal via
    str() rather than a direct Decimal(raw) call — see FieldSpec's
    min_value/max_value docstring in ir.py for why: Decimal(a_float)
    preserves that float's exact binary representation rather than
    the clean decimal value the person actually wrote in the YAML
    file, and str() recovers it since Python's float-to-str is
    round-trip-safe for ordinary decimal literals.
    """
    if raw is None:
        return None
    return Decimal(str(raw))


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

                min_value=_parse_bound(field.get("min_value")),
                max_value=_parse_bound(field.get("max_value")),
                pattern=field.get("pattern"),
            )
        )

    constraints = [
        ConstraintSpec(
            type=constraint["type"],
            columns=constraint["columns"],
            target_table=constraint.get("target_table"),
            target_column=constraint.get("target_column"),
            expression=constraint.get("expression"),
        )
        for constraint in data.get("constraints", [])
    ]

    # Phase 7 remainder — dataset dependency tracking. Top-level key,
    # sibling to `dataset:`/`fields:`/`constraints:` — same placement
    # precedent as `constraints`, which is also parsed from the top
    # level rather than nested inside `dataset:`. NOT the same thing
    # as a field's own `depends_on` above (that's parsed per-field,
    # inside `fields:`).
    raw_dataset_depends_on = data.get("depends_on")
    dataset_depends_on = (
        [str(v) for v in raw_dataset_depends_on]
        if raw_dataset_depends_on is not None
        else []
    )

    return DatasetSpec(
        name=name,
        description=description,
        fields=fields,
        constraints=constraints,
        depends_on=dataset_depends_on,
    )
