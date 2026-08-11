import csv
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
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

    rule: str  # "required" | "uniqueness" | "accepted_values" | "range" | "pattern"
    field: str
    rows: List[int]  # data-row numbers, 1-indexed, header excluded

    # The raw source value that triggered this issue, when there is
    # one (a "required" issue has none — a blank has no value to
    # report). "Raw source value" for v1/v2 specifically, since the
    # CSV loader returns strings — not a claim that quality-check
    # values are inherently strings everywhere in the architecture
    # going forward.
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

    v1/v2 contract: a missing value is exactly an empty CSV field.
    DictReader also produces None for a row with fewer columns than
    the header — that's treated as missing too, but no other
    representation (whitespace, "NULL", "N/A", etc.) is. Whole file
    is loaded into memory; no streaming/chunking.
    """
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _is_missing(value) -> bool:
    return value is None or value == ""


def _try_parse_decimal(raw: str) -> Optional[Decimal]:
    """
    Attempts to parse a raw CSV value as a Decimal, for range
    checking. Returns None on failure. Deliberately a separate
    helper (not inlined into a blanket try/except that also covers
    the missing-value case) so "missing" and "unparseable" stay two
    distinct code paths — callers check _is_missing first, and only
    reach this function for values already known to be present. That
    keeps the door open for a future type-validation rule that would
    need to distinguish "present but not a valid number" as its own
    reportable case, without needing to touch this parsing logic.
    """
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def check_data(table: DatasetSpec, rows: List[Dict[str, str]]) -> QualityResult:
    """
    Checks real data rows against rules expressible in the IR — v1's
    required/uniqueness/accepted_values (all reused from pre-existing
    metadata), plus v2's range (min_value/max_value) and pattern.

    Range/pattern v2 contract:
    - A missing value is never a range/pattern violation — required-
      field validation owns that case (same ownership rule as v1's
      uniqueness check).
    - A value that IS present but fails to parse as a number is
      likewise NOT reported as a range violation. This is a
      deliberate boundary, not silent data loss: type validation
      (verifying a "decimal" column's values are actually numeric at
      all) is a distinct, future rule. v2 only evaluates values that
      successfully parse — see _try_parse_decimal, kept as its own
      function specifically so "missing" vs "unparseable" stay two
      separate, inspectable code paths rather than collapsing into
      one blanket skip.
    - Bounds are inclusive (min_value <= value <= max_value).
    - pattern uses fullmatch semantics — the entire value must match,
      not merely contain a match.

    No type coercion for accepted_values/uniqueness — those remain
    plain string comparisons, unchanged from v1.
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

    # range (Phase 6 v2)
    for f in table.fields:
        if f.min_value is None and f.max_value is None:
            continue

        offenders: Dict[str, List[int]] = {}

        for i, row in enumerate(rows, start=1):
            raw = row.get(f.name)

            if _is_missing(raw):
                continue  # required-field validation owns this case

            numeric = _try_parse_decimal(raw)

            if numeric is None:
                continue  # unparseable — deliberately not a range violation in v2

            out_of_range = (
                (f.min_value is not None and numeric < f.min_value)
                or (f.max_value is not None and numeric > f.max_value)
            )

            if out_of_range:
                offenders.setdefault(raw, []).append(i)

        for value, offending_rows in offenders.items():
            issues.append(
                QualityIssue(
                    rule="range", field=f.name,
                    value=value, rows=offending_rows,
                )
            )

    # pattern (Phase 6 v2)
    for f in table.fields:
        if not f.pattern:
            continue

        offenders: Dict[str, List[int]] = {}

        for i, row in enumerate(rows, start=1):
            value = row.get(f.name)

            if _is_missing(value):
                continue  # required-field validation owns this case

            if not re.fullmatch(f.pattern, value):
                offenders.setdefault(value, []).append(i)

        for value, offending_rows in offenders.items():
            issues.append(
                QualityIssue(
                    rule="pattern", field=f.name,
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
