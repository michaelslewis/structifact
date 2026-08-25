import os
import re
from decimal import Decimal

from ..ir import DatasetSpec, FieldSpec
from ..types import parse_type, parse_bool, parse_list


def _parse_bound(raw):
    """
    Converts a min_value/max_value Markdown table cell into a Decimal.
    Same reasoning as csv.py's _parse_bound: a Markdown cell is always
    a raw string, never a Python float, so Decimal(raw.strip()) is
    already exact -- no float round-trip to guard against the way
    excel.py's _parse_bound has to. See ir.py's FieldSpec.min_value/
    max_value docstring for why Decimal is used at all.
    """
    if not raw:
        return None
    return Decimal(raw.strip())


_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")


def _split_row(line: str) -> list:
    """
    Split one GFM pipe-table row into cells. Tolerates the optional
    leading/trailing `|` GFM allows, and unescapes `\\|` inside a cell
    (e.g. an `accepted_values` cell listing a literal pipe character)
    rather than treating it as a column separator.
    """
    placeholder = "\x00"
    protected = line.replace("\\|", placeholder)

    stripped = protected.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    return [
        cell.strip().replace(placeholder, "|")
        for cell in stripped.split("|")
    ]


def _is_separator_row(cells: list) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(c) for c in cells)


def _find_table(lines: list):
    """
    Locates the first GFM pipe table in the file: a row containing `|`
    immediately followed by a valid `---` separator row of the same
    column count. Everything else -- a heading, prose introducing or
    annotating the table, blank lines before or after -- is ignored.
    Only the first table found is used; a file with more than one
    table (not a shape this adapter's contract anticipates) only ever
    sees the first.

    This is deliberately narrow rather than a general Markdown parser:
    Structifact's Markdown input is a field grid (same contract as
    the CSV/Excel adapters), not arbitrary Markdown content. A
    freeform requirements document -- prose, notes, a loosely-shaped
    table -- is a different thing entirely and goes through
    `structifact discover --ai` instead (see EXAMPLES.md's "Example 9"
    and this module's own docstring below).
    """
    for i in range(len(lines) - 1):
        if "|" not in lines[i]:
            continue

        header_cells = _split_row(lines[i])
        if len(header_cells) < 2:
            continue

        sep_cells = _split_row(lines[i + 1])
        if len(sep_cells) != len(header_cells):
            continue
        if not _is_separator_row(sep_cells):
            continue

        data_lines = []
        for line in lines[i + 2:]:
            if not line.strip() or "|" not in line:
                break
            data_lines.append(line)

        return header_cells, data_lines

    return None, []


def load_markdown(path: str) -> DatasetSpec:
    """
    Loads a DatasetSpec from a Markdown field-grid table -- the same
    column contract as the CSV/Excel adapters (`column_name` and
    `type` required, everything else optional), just written as a GFM
    pipe table instead of a spreadsheet grid. See EXAMPLES.md for the
    full column reference and `examples/customers.md` for a minimal
    real one.

    This is NOT the same thing as a freeform Markdown requirements
    document (prose, a loosely-shaped table, notes) that
    `structifact discover --ai` extracts from -- same duality that
    already exists for `.xlsx` between this deterministic path
    (`load_excel`, a clean field-grid workbook) and
    `discover.extract_text_from_xlsx()` (a raw requirements workbook
    dumped to text for an LLM). Which path runs depends on which
    command you invoke, not on the file extension alone: `validate`/
    `generate`/`validate-data` always expect a field-grid `.md` here;
    `discover --ai` always treats a `.md` file as freeform text,
    regardless of its actual shape.
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    headers, data_lines = _find_table(lines)

    if headers is None:
        raise ValueError(
            f"No Markdown table found in {path!r} -- expected a "
            "'column_name' / 'type' field table (see EXAMPLES.md)."
        )

    if "column_name" not in headers or "type" not in headers:
        raise ValueError(
            f"Markdown table in {path!r} is missing the required "
            "'column_name' and/or 'type' column."
        )

    fields = []

    for line in data_lines:
        cells = _split_row(line)
        row = dict(zip(headers, cells))

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

    table_name = os.path.splitext(os.path.basename(path))[0]

    return DatasetSpec(name=table_name, fields=fields)
