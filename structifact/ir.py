from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class FieldSpec:
    """
    Represents a single dataset field.

    FieldSpec contains intrinsic characteristics of a field.
    Relational or business rules should be represented separately
    through ConstraintSpec.
    """

    name: str
    type: str

    raw_type: Optional[str] = None

    description: Optional[str] = None
    label: Optional[str] = None

    role: Optional[str] = None  # dimension | measure
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None

    accepted_values: Optional[List[str]] = None

    nullable: bool = True

    # Computed/derived fields (Phase 7 — Transformation Framework,
    # first minimal step). This represents that a field's value is
    # derived rather than sourced directly — it does NOT yet support
    # generating SQL from it (see generators/sql.py, unchanged by
    # this step).
    #
    # `expression` is assumed to be valid SQL syntax, meant to be
    # inlined as-is by a future generator. This is deliberately NOT
    # the same thing as the freeform business-logic text
    # `discover --requirements --ai` extracts into its draft output
    # (e.g. "if order_type in ('RET','CRM') then -1 else 1" is
    # readable pseudocode, not valid SQL as written). Turning a
    # discovery draft's raw logic into a real `expression` here is a
    # human decision (or a separate, later translation step) — never
    # automatic.
    computed: bool = False
    expression: Optional[str] = None
    depends_on: Optional[List[str]] = None


@dataclass
class ConstraintSpec:
    """
    Represents a dataset-level constraint.

    Constraints describe rules or relationships that do not
    belong directly on an individual field.

    Examples:
    - primary_key
    - unique
    - foreign_key
    - check

    foreign_key and check (Phase 1 — ConstraintSpec Foundation,
    closing the previously-tracked gap):

    `target_table` / `target_column` are used only when
    type == "foreign_key". Both are free-text strings, not validated
    against another known dataset — Structifact validates one
    dataset at a time today and has no cross-dataset resolution
    anywhere in the IR yet (that's closer to Phase 7/9 "dataset
    dependency" territory, a separate and larger concern). Only
    single-column foreign keys are supported; `columns` must contain
    exactly one entry for a foreign_key constraint. Composite FKs
    are deliberately out of scope until a real example needs them,
    matching how computed-field `expression` support was scoped.

    `expression` is used only when type == "check". Like
    FieldSpec.expression, it is assumed-valid SQL, inlined as-is by
    a generator — Structifact does not parse or validate the SQL
    itself, only that it's present and non-empty.
    """

    type: str
    columns: List[str]

    target_table: Optional[str] = None
    target_column: Optional[str] = None

    expression: Optional[str] = None


@dataclass
class DatasetSpec:
    """
    Canonical intermediate representation for a Structifact dataset.

    DatasetSpec replaces the previous TableSpec concept while
    remaining implementation-neutral. A dataset may eventually
    represent more than a relational database table.
    """

    name: str
    fields: List[FieldSpec]

    description: Optional[str] = None

    constraints: List[ConstraintSpec] = field(default_factory=list)


# Backwards compatibility during migration.
#
# TableSpec is intentionally an alias rather than a subclass because
# there is no specialized Table behavior. Existing code importing
# TableSpec should continue to work while DatasetSpec becomes the
# canonical IR name.
TableSpec = DatasetSpec
