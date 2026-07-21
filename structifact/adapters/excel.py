import os

from ..ir import DatasetSpec, FieldSpec


def load_excel(path: str) -> DatasetSpec:
    import pandas as pd

    df = pd.read_excel(path)

    fields = []

    for row in df.to_dict(orient="records"):
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