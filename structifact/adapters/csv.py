import csv
import os

from ..ir import DatasetSpec, FieldSpec
from ..types import parse_type, parse_bool, parse_list


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
                )
            )

    table_name = os.path.splitext(
        os.path.basename(path)
    )[0]

    return DatasetSpec(
        name=table_name,
        fields=fields
    )
