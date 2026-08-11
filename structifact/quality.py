import csv
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .ir import DatasetSpec


@dataclass
class QualityIssue:
    """
    One data-quality finding, already grouped by field (+ offending
    value, where relevant) — never one entry per row. E.g. three
    rows sharing a duplicate primary key produce one QualityIssue
    with rows=[2, 5, 9], not three separate issues.
    """

    rule: str  # "required" | "uniqueness" | "accepted_values"
    field: str
    rows: List[int]  # data-row numbers, 1-indexed, header excluded

    # The raw source value that triggered this issue, when there is
    # one (a "required" issue has none — a blank has no value to
    # report). "Raw source value" for v1 specifically, since the CSV
    # loader returns strings with no type coercion — not a claim
    # that quality-check values are inherently strings everywhere in
    # the architecture going forward.
    value: Optional[str] = None


@dataclass
class QualityResult:
    dataset: str
    rows_checked: int
    issues: List[QualityIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


def load_data_rows(path: str) -> List[Dict[str, str]]:
    """
    Reads a CSV data file as raw rows for quality checking — string
    values only, no type coercion, no inference. Deliberately NOT
    the same thing as discover.py's sampler (which infers a schema
    from data); this reads data to check it against metadata that
    already exists.

    v1 contract: a missing value is exactly an empty CSV field.
    DictReader also produces None for a row with fewer columns than
    the header — that's treated as missing too, but no other
    representation (whitespace, "NULL", "N/A", etc.) is. Whole file
    is loaded into memory; no streaming/chunking in v1.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _is_missing(value) -> bool:
    return value is None or value == ""


def check_data(table: DatasetSpec, rows: List[Dict[str, str]]) -> QualityResult:
    """
    Checks real data rows against rules already expressible in the
    existing IR — no new metadata concepts. Three rule types:

    - required: FieldSpec.nullable == False. A missing value (see
      _is_missing) at that field is a violation.
    - uniqueness: ConstraintSpec type primary_key or unique. A row
      whose key column(s) are all present and match another row's
      is a violation; rows with any missing key column are skipped
      here — required-field validation owns that case, avoiding
      double-reporting the same underlying problem.
    - accepted_values: FieldSpec.accepted_values. A present value
      not in the set is a violation; a missing value is not
      (nullable ownership again — a blank on a nullable field with
      accepted_values is not itself invalid).

    No type coercion anywhere — every comparison is a plain string
    comparison on the raw CSV value. This is a real architectural
    boundary, not just an unimplemented feature: range/regex
    validation isn't just "not built yet," it isn't meaningful until
    there's a type-interpretation step, which v1 deliberately doesn't
    have.
    """
    issues: List[QualityIssue] = []

    # required
    for f in table.fields:
        if f.nullable:
            continue

        missing_rows = [
            i for i, row in enumerate(rows, start=1)
            if _is_missing(row.get(f.name))
        ]

        if missing_rows:
            issues.append(
                QualityIssue(rule="required", field=f.name, rows=missing_rows)
            )

    # accepted_values
    for f in table.fields:
        if not f.accepted_values:
            continue

        offenders: Dict[str, List[int]] = {}

        for i, row in enumerate(rows, start=1):
            value = row.get(f.name)

            if _is_missing(value):
                continue  # nullable ownership — not an accepted_values concern

            if value not in f.accepted_values:
                offenders.setdefault(value, []).append(i)

        for value, offending_rows in offenders.items():
            issues.append(
                QualityIssue(
                    rule="accepted_values", field=f.name,
                    value=value, rows=offending_rows,
                )
            )

    # uniqueness (primary_key / unique constraints)
    for constraint in table.constraints:
        if constraint.type not in ("primary_key", "unique"):
            continue

        columns = constraint.columns
        seen: Dict[Tuple[str, ...], List[int]] = {}

        for i, row in enumerate(rows, start=1):
            values = tuple(row.get(col) for col in columns)

            if any(_is_missing(v) for v in values):
                continue  # required-field validation owns missing key values

            seen.setdefault(values, []).append(i)

        for values, offending_rows in seen.items():
            if len(offending_rows) < 2:
                continue

            field_label = ", ".join(columns)
            value_label = ", ".join(values)

            issues.append(
                QualityIssue(
                    rule="uniqueness", field=field_label,
                    value=value_label, rows=offending_rows,
                )
            )

    return QualityResult(
        dataset=table.name,
        rows_checked=len(rows),
        issues=issues,
    )
