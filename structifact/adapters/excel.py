def load_excel(path: str) -> TableSpec:
    import pandas as pd
import os

from ..ir import TableSpec, FieldSpec


def load_excel(path: str) -> TableSpec:
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


    table_name = os.path.splitext(os.path.basename(path))[0]

    return TableSpec(
        name=table_name,
        fields=fields
    )