import math
import os
from decimal import Decimal

from ..ir import DatasetSpec, FieldSpec
from ..types import parse_type, parse_bool, parse_list


def _cell(row: dict, key: str):
    """
    Read a raw cell from an openpyxl-derived row dict, normalizing a
    blank cell to None.

    openpyxl (with `values_only=True`) hands back a genuinely blank
    cell as Python `None` already, which the first check below
    handles directly. The NaN check is a defensive leftover from
    this adapter's original pandas-based implementation, where a
    blank cell arrived as NaN (a float) instead — pandas' `NaN or ""`
    evaluates to NaN itself (NaN is truthy), and `str(NaN)` is the
    literal text "nan", so without this normalization a blank cell in
    ANY optional column (description, role, nullable, etc.) would be
    silently written into the IR as the string "nan" instead of being
    treated as "not specified". Kept here rather than deleted: a
    cached formula-result cell could in principle read back as NaN
    (e.g. a `0/0`-style error), and the check is a correct, harmless
    safety net either way — see `docs/DECISION_HISTORY.md`'s "Removing
    pandas from the Metadata-Spec Excel Adapter" entry for why this
    adapter moved off pandas at all.
    """
    value = row.get(key)

    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    return value


def _parse_bound(raw):
    """
    Converts a min_value/max_value Excel cell into a Decimal. `raw`
    has already passed through _cell, so it's either None (blank
    cell) or a real value — openpyxl typically hands back a Python
    float for a numeric-formatted cell, same as pandas did before
    this adapter moved off it. Routing through str() before
    Decimal(), not Decimal(raw) directly, avoids preserving that
    float's exact binary representation instead of the clean decimal
    value the person actually entered — same reasoning as yaml.py's
    _parse_bound (see ir.py's FieldSpec.min_value/max_value
    docstring for the full explanation).
    """
    if raw is None:
        return None
    return Decimal(str(raw))


def load_excel(path: str) -> DatasetSpec:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)

    try:
        rows = wb.active.iter_rows(values_only=True)
        headers = next(rows)

        fields = []

        for raw_row in rows:
            row = dict(zip(headers, raw_row))
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

                    min_value=_parse_bound(_cell(row, "min_value")),
                    max_value=_parse_bound(_cell(row, "max_value")),
                    pattern=_cell(row, "pattern"),
                )
            )
    finally:
        wb.close()

    table_name = os.path.splitext(
        os.path.basename(path)
    )[0]

    return DatasetSpec(
        name=table_name,
        fields=fields
    )
