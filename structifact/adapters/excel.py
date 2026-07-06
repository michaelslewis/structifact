import pandas as pd

from ..ir import TableSpec, FieldSpec


def load_excel(path: str) -> TableSpec:
    df = pd.read_excel(path)

    fields = []

    for _, row in df.iterrows():
        fields.append(
            FieldSpec(
                name=row["column_name"],
                type=row["type"],
                description=row.get("description", "") or ""
            )
        )

    # infer table name from filename
    table_name = path.split("/")[-1].replace(".xlsx", "")

    return TableSpec(
        name=table_name,
        fields=fields
    )