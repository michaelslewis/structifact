import os

from ..ir import DatasetSpec, FieldSpec
from ..types import parse_type


def load_excel(path: str) -> DatasetSpec:
    import pandas as pd

    df = pd.read_excel(path)

    fields = []

    for row in df.to_dict(orient="records"):
        parsed = parse_type(row["type"])

        fields.append(
            FieldSpec(
                name=row["column_name"],
                type=parsed["type"],
                raw_type=row["type"],
                description=row.get("description", "") or "",

                length=parsed.get("length"),
                precision=parsed.get("precision"),
                scale=parsed.get("scale"),
            )
        )

    table_name = os.path.splitext(
        os.path.basename(path)
    )[0]

    return DatasetSpec(
        name=table_name,
        fields=fields
    )
