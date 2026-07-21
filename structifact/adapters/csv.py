import csv
import os

from ..ir import DatasetSpec, FieldSpec


def load_csv(path: str) -> DatasetSpec:
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

    return DatasetSpec(
        name=table_name,
        fields=fields
    )