import csv
import os

from ..ir import TableSpec, FieldSpec


def load_csv(path: str) -> TableSpec:
    fields = []

    with open(path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            fields.append(
                FieldSpec(
                    name=row["column_name"],
                    type=row["type"],
                    description=row.get("description", "") or ""
                )
            )

    table_name = os.path.splitext(
        os.path.basename(path)
    )[0]

    return TableSpec(
        name=table_name,
        fields=fields
    )