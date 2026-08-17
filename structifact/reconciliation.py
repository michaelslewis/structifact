from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

import yaml

from .ir import DatasetSpec


@dataclass
class FieldMapping:
    """One old-system field <-> new-system field correspondence.
    Column names are not assumed to match across a legacy/modern
    migration (they essentially never do) — every field reconcile_data
    compares must be named explicitly, on both sides, in a
    ReconciliationMapping."""

    old: str
    new: str


@dataclass
class ReconciliationMapping:
    """
    key is the field pair used to match a row in the old dataset to
    a row in the new one (single-column only for v1 — matching
    ConstraintSpec.foreign_key's own single-column-only starting
    point until a real example needs composite keys).

    fields lists every other old/new field pair reconcile_data may
    need. v1 only actually uses this for aggregate comparison (see
    reconcile_data) — full column-level value comparison on matched
    rows is v2, not yet built.
    """

    key: FieldMapping
    fields: List[FieldMapping]


def load_reconciliation_mapping(path: str) -> ReconciliationMapping:
    """
    Loads a reconciliation mapping YAML file:

        key:
          old: ORD_ID
          new: order_id
        fields:
          - old: ORD_AMT
            new: order_amount

    Deliberately a standalone small YAML shape, not a DatasetSpec —
    it describes a relationship between two independent datasets'
    fields, not one dataset's own structure. Raises ValueError on a
    malformed file (missing key/old/new) — a configuration error,
    never silently treated as "no fields to compare." Does not
    validate that the named fields actually exist in either schema —
    see validate_mapping for that, which needs both loaded
    DatasetSpecs to check against.
    """
    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    if "key" not in raw or "old" not in raw["key"] or "new" not in raw["key"]:
        raise ValueError(
            f"Reconciliation mapping '{path}' must declare a 'key' with "
            f"both 'old' and 'new' field names."
        )

    key = FieldMapping(old=raw["key"]["old"], new=raw["key"]["new"])

    fields = []
    for entry in raw.get("fields", []):
        if "old" not in entry or "new" not in entry:
            raise ValueError(
                f"Reconciliation mapping '{path}' has a 'fields' entry "
                f"missing 'old' or 'new'."
            )
        fields.append(FieldMapping(old=entry["old"], new=entry["new"]))

    return ReconciliationMapping(key=key, fields=fields)


def validate_mapping(
    mapping: ReconciliationMapping,
    old_table: DatasetSpec,
    new_table: DatasetSpec,
) -> None:
    """
    Confirms every field mapping.key/mapping.fields names actually
    resolves to a declared field in the corresponding schema — same
    "never trust a bare name, resolve it against real declared
    metadata" discipline as quality.py's resolve_references(). A bad
    mapping is a configuration error, raised here, before any
    reconciliation runs — never silently producing a misleading
    report.
    """
    old_field_names = {f.name for f in old_table.fields}
    new_field_names = {f.name for f in new_table.fields}

    if mapping.key.old not in old_field_names:
        raise ValueError(
            f"Mapping key.old '{mapping.key.old}' is not a declared "
            f"field in '{old_table.name}'."
        )
    if mapping.key.new not in new_field_names:
        raise ValueError(
            f"Mapping key.new '{mapping.key.new}' is not a declared "
            f"field in '{new_table.name}'."
        )

    for fm in mapping.fields:
        if fm.old not in old_field_names:
            raise ValueError(
                f"Mapping field '{fm.old}' is not a declared field in "
                f"'{old_table.name}'."
            )
        if fm.new not in new_field_names:
            raise ValueError(
                f"Mapping field '{fm.new}' is not a declared field in "
                f"'{new_table.name}'."
            )


@dataclass
class ReconciliationIssue:
    """
    One reconciliation finding. Two distinct shapes share this class
    the same way QualityIssue's optional fields cover several rule
    types — category separates them at the report level ("row
    coverage" vs "aggregate"), matching the ask to keep those kinds
    of evidence visibly distinct rather than one undifferentiated
    issue list.

    row_coverage issues (missing_in_new / missing_in_old) set `keys`;
    aggregate issues (aggregate_mismatch) set `field`/`old_value`/
    `new_value`/`diff`.
    """

    category: str  # "row_coverage" | "aggregate"
    rule: str  # "missing_in_new" | "missing_in_old" | "aggregate_mismatch"

    keys: Optional[List[str]] = None

    field: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    diff: Optional[str] = None


@dataclass
class ReconciliationResult:
    old_dataset: str
    new_dataset: str

    old_count: int
    new_count: int
    matched_count: int

    issues: List[ReconciliationIssue] = field(default_factory=list)

    @property
    def is_reconciled(self) -> bool:
        return not self.issues


def _try_parse_decimal(raw) -> Optional[Decimal]:
    """Same skip-rather-than-flag treatment quality.py's range check
    gives an unparseable numeric value — a present-but-unparseable
    measure value is excluded from the aggregate sum, not treated as
    a mismatch in its own right. Type validation is a distinct,
    still-unbuilt concern (see quality.py)."""
    if raw is None or raw == "":
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def reconcile_data(
    old_table: DatasetSpec,
    old_rows: List[Dict[str, str]],
    new_table: DatasetSpec,
    new_rows: List[Dict[str, str]],
    mapping: ReconciliationMapping,
) -> ReconciliationResult:
    """
    v1 reconciliation: given two datasets meant to represent the same
    logical output, checks

    * row-population coverage — which keys exist in old but not new
      (missing_in_new) and vice versa (missing_in_old)
    * aggregate equivalence, on the MATCHED population only, for
      every mapped field the new schema declares role: measure

    Aggregating over the matched population specifically (not the
    full old/new populations) is deliberate: summing everything would
    conflate a genuine value discrepancy on a matched row with the
    structural noise of rows that were legitimately added or dropped
    during the migration — both of which are already reported,
    separately and exactly, by the row-coverage check above. Matching
    on the matched population isolates "do the numbers agree for the
    records both systems agree exist," which is the more diagnostic
    question.

    v1 does NOT claim semantic equivalence between the two datasets.
    It establishes row-population coverage, key correspondence, and
    aggregate equivalence for declared measures on the matched
    population — it does not compare individual field values row by
    row. A dataset could pass every v1 check while still differing on
    some non-measure column, or even on a measure column in a way
    that happens to net to zero across the matched population. Full
    column-level comparison on matched rows is v2, not yet built.

    Duplicate or blank key values on either side are not specially
    handled in v1 — a duplicate key silently collapses to whichever
    row a dict comprehension keeps last, and a blank key on both
    sides would incorrectly appear to match. No real example has yet
    required either case; see FUTURE_WORK.md.
    """
    old_key = mapping.key.old
    new_key = mapping.key.new

    old_by_key = {row.get(old_key): row for row in old_rows}
    new_by_key = {row.get(new_key): row for row in new_rows}

    old_keys = set(old_by_key)
    new_keys = set(new_by_key)

    missing_in_new = sorted(k for k in (old_keys - new_keys) if k is not None)
    missing_in_old = sorted(k for k in (new_keys - old_keys) if k is not None)
    matched_keys = sorted(k for k in (old_keys & new_keys) if k is not None)

    issues: List[ReconciliationIssue] = []

    if missing_in_new:
        issues.append(
            ReconciliationIssue(
                category="row_coverage", rule="missing_in_new", keys=missing_in_new,
            )
        )

    if missing_in_old:
        issues.append(
            ReconciliationIssue(
                category="row_coverage", rule="missing_in_old", keys=missing_in_old,
            )
        )

    new_field_by_name = {f.name: f for f in new_table.fields}

    for fm in mapping.fields:
        new_field = new_field_by_name.get(fm.new)
        if new_field is None or new_field.role != "measure":
            continue

        old_sum = Decimal("0")
        new_sum = Decimal("0")

        for key in matched_keys:
            old_val = _try_parse_decimal(old_by_key[key].get(fm.old))
            new_val = _try_parse_decimal(new_by_key[key].get(fm.new))

            if old_val is not None:
                old_sum += old_val
            if new_val is not None:
                new_sum += new_val

        if old_sum != new_sum:
            diff = new_sum - old_sum
            issues.append(
                ReconciliationIssue(
                    category="aggregate", rule="aggregate_mismatch",
                    field=fm.new,
                    old_value=str(old_sum), new_value=str(new_sum),
                    diff=format(diff, "+"),
                )
            )

    return ReconciliationResult(
        old_dataset=old_table.name,
        new_dataset=new_table.name,
        old_count=len(old_rows),
        new_count=len(new_rows),
        matched_count=len(matched_keys),
        issues=issues,
    )
