import csv
import os
from decimal import Decimal

from ..ir import DatasetSpec, FieldSpec
from ..types import parse_type, parse_bool, parse_list


def _parse_bound(raw):
    """
    Converts a metadata-CSV cell into a Decimal. Unlike yaml.py's
    _parse_bound, there's no float-precision concern to route around
    here — the CSV adapter never sees a Python float in the first
    place, just the raw string cell, so Decimal(raw.strip()) is
    already exact. See ir.py's FieldSpec.min_value/max_value
    docstring for the full explanation of why Decimal (not float) is
    used at all.
    """
    if not raw:
        return None
    return Decimal(raw.strip())


def load_csv(path: str) -> DatasetSpec:
    fields = []

    with open(path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            parsed = parse_type(row["type"])
            column_name = row["column_name"]

            fields.append(
                FieldSpec(
                    name=column_name,
                    type=parsed["type"],
                    raw_type=row["type"],
                    description=row.get("description", "") or "",

                    role=row.get("role") or None,
                    accepted_values=parse_list(row.get("accepted_values")),

                    length=parsed.get("length"),
                    precision=parsed.get("precision"),
                    scale=parsed.get("scale"),

                    nullable=parse_bool(
                        row.get("nullable"),
                        field_name=f"{column_name}.nullable",
                        default=True,
                    ),

                    computed=parse_bool(
                        row.get("computed"),
                        field_name=f"{column_name}.computed",
                        default=False,
                    ),
                    expression=row.get("expression") or None,
                    depends_on=parse_list(row.get("depends_on")),

                    min_value=_parse_bound(row.get("min_value")),
                    max_value=_parse_bound(row.get("max_value")),
                    pattern=row.get("pattern") or None,
                )
            )

    table_name = os.path.splitext(
        os.path.basename(path)
    )[0]

    return DatasetSpec(
        name=table_name,
        fields=fields
    )
