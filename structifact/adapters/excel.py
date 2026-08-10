import math
import os

from ..ir import DatasetSpec, FieldSpec
from ..types import parse_type, parse_bool, parse_list


def _cell(row: dict, key: str):
    """
    Read a raw cell from a pandas-derived row dict, normalizing a
    blank cell to None regardless of how pandas represented it.

    pandas represents a blank Excel cell as NaN (a float), not None
    or "" — passed through unchanged, `NaN or ""` evaluates to NaN
    itself (NaN is truthy), and `str(NaN)` is the literal text "nan".
    Without this normalization, a blank cell in ANY optional column
    (description, role, nullable, etc.) would be silently written
    into the IR as the string "nan" instead of being treated as
    "not specified".
    """
    value = row.get(key)

    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    return value


def load_excel(path: str) -> DatasetSpec:
    import pandas as pd

    df = pd.read_excel(path)

    fields = []

    for row in df.to_dict(orient="records"):
        parsed = parse_type(row["type"])
        column_name = row["column_name"]

        fields.append(
            FieldSpec(
                name=column_name,
                type=parsed["type"],
                raw_type=row["type"],
                description=_cell(row, "description") or "",

                role=_cell(row, "role"),
                accepted_values=parse_list(_cell(row, "accepted_values")),

                length=parsed.get("length"),
                precision=parsed.get("precision"),
                scale=parsed.get("scale"),

                nullable=parse_bool(
                    _cell(row, "nullable"),
                    field_name=f"{column_name}.nullable",
                    default=True,
                ),

                computed=parse_bool(
                    _cell(row, "computed"),
                    field_name=f"{column_name}.computed",
                    default=False,
                ),
                expression=_cell(row, "expression"),
                depends_on=parse_list(_cell(row, "depends_on")),
            )
        )

    table_name = os.path.splitext(
        os.path.basename(path)
    )[0]

    return DatasetSpec(
        name=table_name,
        fields=fields
    )
