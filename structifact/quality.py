import csv
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Set, Tuple

from .ir import DatasetSpec


@dataclass
class QualityIssue:
    """
    One data-quality finding, already grouped by field (+ offending
    value, where relevant) — never one entry per row. E.g. three
    rows sharing a duplicate primary key produce one QualityIssue
    with rows=[2, 5, 9], not three separate issues.
    """

    rule: str  # "required" | "uniqueness" | "accepted_values" | "range" | "pattern" | "foreign_key"
    field: str
    rows: List[int]  # data-row numbers, 1-indexed, header excluded

    # The raw source value that triggered this issue, when there is
    # one (a "required" issue has none — a blank has no value to
    # report). "Raw source value" for v1/v2/v3 specifically, since
    # the CSV loader returns strings — not a claim that quality-check
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

    v1/v2/v3 contract: a missing value is exactly an empty CSV field.
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


def resolve_references(
    table: DatasetSpec,
    refs: Dict[str, Tuple[DatasetSpec, List[Dict[str, str]]]],
) -> Dict[str, Set[str]]:
    """
    Resolves `table`'s foreign_key constraints against supplied
    reference data (Phase 6 v3), producing exactly the
    referenced_values shape check_data() needs: target_table name ->
    set of raw values present in that table's target_column.

    This function is schema-aware, per the v3 contract — it never
    trusts a CSV header alone. For every foreign_key constraint on
    `table`, it checks, in order:

    1. `refs` actually contains an entry for the constraint's
       target_table. Missing --ref for a declared FK is a hard
       configuration error, not a silently-skipped check — running
       validate-data without it must NOT report success, since
       Structifact genuinely couldn't perform the check it was asked
       to perform.
    2. The supplied reference schema's own `name` actually matches
       the target_table it was supplied under (catches a --ref alias
       pointing at the wrong file).
    3. target_column is a real field DECLARED IN THE REFERENCE
       SCHEMA — never inferred from what happens to be a CSV header.
       A mismatched/missing target_column is a bad relationship
       DEFINITION, and is raised as an error here, not silently
       treated as "zero valid values" (which would make every row a
       false foreign_key violation).

    Every failure here raises ValueError — a usage/configuration
    error, never a QualityIssue. A bad relationship definition is not
    a data problem, and must never be reported as one.

    Composite foreign keys are out of scope (matching ConstraintSpec,
    which has only supported single-column FK since Phase 1) — this
    function assumes exactly one source column / one target column
    per foreign_key constraint, already enforced by validation.py.
    """
    referenced_values: Dict[str, Set[str]] = {}

    for constraint in table.constraints:
        if constraint.type != "foreign_key":
            continue

        target_table = constraint.target_table
        target_column = constraint.target_column

        if target_table not in refs:
            raise ValueError(
                f"Foreign-key constraint on '{constraint.columns[0]}' "
                f"targets dataset '{target_table}', but no reference "
                f"data was supplied for it. Pass "
                f"--ref {target_table}=<schema.yml>:<data.csv>."
            )

        ref_schema, ref_rows = refs[target_table]

        if ref_schema.name != target_table:
            raise ValueError(
                f"--ref '{target_table}' points to a schema whose "
                f"dataset name is '{ref_schema.name}', not "
                f"'{target_table}' — the schema's declared name must "
                f"match the --ref alias."
            )

        ref_field_names = {f.name for f in ref_schema.fields}

        if target_column not in ref_field_names:
            raise ValueError(
                f"Foreign-key target_column '{target_column}' does "
                f"not exist in dataset '{target_table}' — declared "
                f"fields are: {', '.join(sorted(ref_field_names))}"
            )

        referenced_values[target_table] = {
            row.get(target_column)
            for row in ref_rows
            if not _is_missing(row.get(target_column))
        }

    return referenced_values


def check_data(
    table: DatasetSpec,
    rows: List[Dict[str, str]],
    referenced_values: Optional[Dict[str, Set[str]]] = None,
) -> QualityResult:
    """
    Checks real data rows against rules expressible in the IR — v1's
    required/uniqueness/accepted_values, v2's range/pattern, and v3's
    foreign_key (relationship/existence) checking.

    Range/pattern v2 contract:
    - A missing value is never a range/pattern violation — required-
      field validation owns that case (same ownership rule as v1's
      uniqueness check).
    - A value that IS present but fails to parse as a number is
      likewise NOT reported as a range violation. This is a
      deliberate boundary: type validation (verifying a "decimal"
      column's values are actually numeric at all) is a distinct,
      future rule. See _try_parse_decimal.
    - Bounds are inclusive (min_value <= value <= max_value).
    - pattern uses fullmatch semantics — the entire value must match.

    Foreign-key v3 contract:
    - `referenced_values` is precomputed by the caller — typically
      via resolve_references() — as target_table -> set of valid raw
      values. check_data() itself does no schema loading; it's pure
      membership checking, matching the same "core checker only
      evaluates, callers prepare data" separation the rest of this
      module already follows.
    - A missing source value is skipped — required-field validation
      owns that case, same ownership rule as everywhere else.
    - This is EXISTENCE checking only, not uniqueness: a target value
      appearing more than once in the referenced data is not this
      function's concern — the referenced dataset's own primary_key/
      unique constraints are responsible for that, checked separately
      if/when someone runs validate-data against that dataset itself.
    - If a table has a foreign_key constraint whose target_table has
      no entry in `referenced_values` (e.g. caller didn't call
      resolve_references() first), that constraint is silently
      skipped here — resolve_references() is where a missing --ref
      is supposed to raise, not this function; check_data() stays
      defensive/simple rather than duplicating that check.

    No type coercion for accepted_values/uniqueness/foreign_key —
    those remain plain string comparisons.
    """
    issues: List[QualityIssue] = []
    referenced_values = referenced_values or {}

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

    # foreign_key (Phase 6 v3) — existence/membership only, never a
    # uniqueness check on the target side (see docstring).
    for constraint in table.constraints:
        if constraint.type != "foreign_key":
            continue

        target_table = constraint.target_table

        if target_table not in referenced_values:
            continue  # resolve_references() is where this should have raised

        valid_values = referenced_values[target_table]
        source_column = constraint.columns[0]

        offenders: Dict[str, List[int]] = {}

        for i, row in enumerate(rows, start=1):
            value = row.get(source_column)

            if _is_missing(value):
                continue  # required-field validation owns this case

            if value not in valid_values:
                offenders.setdefault(value, []).append(i)

        for value, offending_rows in offenders.items():
            issues.append(
                QualityIssue(
                    rule="foreign_key", field=source_column,
                    value=value, rows=offending_rows,
                )
            )

    return QualityResult(
        dataset=table.name,
        rows_checked=len(rows),
        issues=issues,
    )
