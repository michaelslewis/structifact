from dataclasses import dataclass, field
from decimal import Decimal
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

    # Cross-source field attribution (Phase 7 — sources/joins
    # milestone). Both None (the default) means "this field comes
    # from the dataset's own primary source, under a column with the
    # same name as the field" — i.e. today's existing behavior for
    # every dataset that doesn't use sources/joins at all.
    #
    # `source`, when set, must name a SourceRef.name declared in the
    # same dataset's `sources` list (never a SourceRef.table directly
    # — see SourceRef's docstring for why those are different).
    # `source_column` is the column name on that source; if omitted
    # while `source` is set, it defaults to this field's own `name`.
    #
    # Deliberately NOT used together with `computed`/`expression` in
    # this milestone — a computed field's expression is raw SQL that
    # may already reference joined-in columns by their source alias
    # directly (e.g. "labor_amount_lc * resolved_fx_rate"), so it
    # doesn't need source/source_column duplicating that. Combining
    # them is a real question for a future milestone, not this one.
    source: Optional[str] = None
    source_column: Optional[str] = None

    # Value-level data-quality rules (Phase 6 v2). Unlike v1's
    # required/uniqueness/accepted_values (all reused from metadata
    # that already existed for other reasons), these three fields
    # exist purely to support structifact/quality.py's check_data() —
    # they have no other purpose in the IR.
    #
    # min_value / max_value are inclusive bounds, either may be set
    # independently. Stored as Decimal, NOT float: adapters must
    # convert via Decimal(str(v)) rather than Decimal(v) directly —
    # PyYAML parses a YAML numeric literal into a Python float before
    # Structifact ever sees it, and Decimal(some_float) preserves
    # that float's exact (and often ugly) binary representation
    # rather than the clean decimal value the person actually wrote.
    # Routing through str() first recovers that, since Python's
    # float-to-str conversion is round-trip-safe for ordinary decimal
    # literals. Only meaningful on integer/decimal fields — checked
    # in validation.py, not here.
    #
    # `pattern` is a raw regex, checked with fullmatch semantics (the
    # entire field value must match, not merely contain a match) —
    # matched against real data in quality.py, and also checked for
    # basic compilability in validation.py, since (unlike `expression`
    # or the sources/joins milestone's raw SQL fragments) a regex
    # pattern actually CAN be meaningfully validated without running
    # anything. Only meaningful on string fields.
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    pattern: Optional[str] = None


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
    anywhere in the IR yet (that's Phase 6 v3 territory — relationship
    validation is expected to be the milestone that finally gives
    these fields real meaning at the data level). Only single-column
    foreign keys are supported; `columns` must contain exactly one
    entry for a foreign_key constraint. Composite FKs are deliberately
    out of scope until a real example needs them, matching how
    computed-field `expression` support was scoped.

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
class DedupRule:
    """
    Priority-based row selection within a joined-in source
    (Phase 7 — sources/joins milestone).

    This is NOT a uniqueness constraint — it's a row-selection rule:
    given a group of rows sharing the same partition_by key(s),
    exactly one wins, chosen by order_by priority (first entry =
    highest priority; ties broken by subsequent entries). Maps
    directly onto:

        ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) = 1

    which is the exact pattern examples/workorder_demo's reference
    SQL uses by hand for each PARTNER_ROLE join (prefer
    is_current = 'Y', fall back to the most recently updated row).

    `order_by` entries are raw SQL fragments (e.g. "is_current
    desc"), same trust model as FieldSpec.expression — Structifact
    does not parse or validate them, only checks they're present.
    """

    partition_by: List[str]
    order_by: List[str]


@dataclass
class SourceRef:
    """
    A named, joinable source within a dataset's transformation
    (Phase 7 — sources/joins milestone).

    The `name` vs `table` distinction is the reason this class
    exists as its own concept rather than just a table name: `table`
    is the physical table being read from; `name` is the logical
    alias for THIS PARTICULAR JOINED-IN INSTANCE of that table
    within this dataset. They're different specifically so the same
    physical table can be joined into one dataset multiple times
    under different roles — e.g. `table: partner_role` appearing as
    three separate SourceRefs (`name: partner_requested_by`,
    `name: partner_billed_to`, `name: partner_site_contact`), each
    with its own `filter` and `dedup` rule. `name` is what
    JoinSpec.source and FieldSpec.source both refer to — always
    `name`, never `table` directly.

    `filter` is an optional raw SQL predicate scoping this instance
    of the source (e.g. "role_code = 'REQ'"). Same trust model as
    `expression`/`on` elsewhere in the IR — not parsed or validated.
    """

    name: str
    table: str
    filter: Optional[str] = None
    dedup: Optional[DedupRule] = None


@dataclass
class JoinSpec:
    """
    Joins a SourceRef into a dataset's primary source
    (Phase 7 — sources/joins milestone).

    `source` refers to a SourceRef.name declared in the same
    dataset's `sources` list (validated — see validation.py).

    `on` is a single raw SQL join condition, inlined as-is by the
    generator. Multiple join keys are expressed with AND inside the
    same string (e.g. "a = b AND c = d") rather than a separate
    structured list — same trust model as FieldSpec.expression.

    `type` is restricted to Structifact's currently-supported join
    types (see validation.py) — not free text, since generating an
    unsupported join keyword would just produce broken SQL silently.

    In YAML, this field's key must be quoted (`"on":`, not `on:`) —
    PyYAML's default (YAML 1.1) resolver parses a bare `on` key as the
    boolean `True`, not the string "on", which silently produces a
    dict key mismatch rather than an obvious error.
    """

    source: str
    on: str
    type: str = "left"


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

    # Phase 7 — Transformation Framework (ModelGenerator). The table
    # this dataset's SELECT-based transformation model reads from as
    # its primary source. Deliberately explicit rather than assumed:
    # guessing that the source table always shares the dataset's
    # name would silently produce wrong SQL for anyone whose source
    # table is named differently (a staging prefix, a legacy name,
    # etc.), which runs against "metadata as the source of truth" —
    # Structifact should be told, not infer. When omitted,
    # ModelGenerator falls back to `name` for the common case where
    # they do match, so this costs nothing for most users.
    source_table: Optional[str] = None

    # Found via real-world use (a real SAP-shaped requirements doc,
    # not a hypothetical): the primary source had its own filter
    # ("current records only") with no field to express it anywhere
    # in the IR -- only a joined-in SourceRef could carry a `filter`.
    # Same trust model as SourceRef.filter/source_table: a raw SQL
    # predicate, inlined as-is, never parsed. Deliberately a plain
    # string on DatasetSpec rather than promoting source_table into a
    # full SourceRef -- the real need was "filter the primary source,"
    # not "unify the primary/secondary source model," and the latter
    # would have been solving a bigger problem than what an actual
    # example asked for.
    source_filter: Optional[str] = None

    # Phase 7 — sources/joins milestone. Additional joinable sources
    # beyond the dataset's own primary source (source_table/name),
    # and the joins connecting them in. Both default to empty lists,
    # so any existing dataset with neither declared produces exactly
    # today's ModelGenerator behavior (a single-source SELECT) —
    # this is purely additive. See SourceRef/JoinSpec docstrings
    # above for the full contract. Deliberately does NOT yet support
    # a computed field's expression referencing a joined field by
    # source alias, or conditional-fallback logic (e.g. FX-rate-style
    # COALESCE) — both are real, but scoped to a later milestone.
    sources: List[SourceRef] = field(default_factory=list)
    joins: List[JoinSpec] = field(default_factory=list)

    # Found via real-world use, confirmed by a second independent real
    # example before being added (not from one file alone): dbt-target
    # metadata a downstream dbt-based catalog/BI tool expects, with no
    # representation anywhere in the IR. Deliberately prefixed `dbt_`
    # rather than given generic names — these are dbt-target concepts,
    # not general Structifact ones, matching how catalog_extended's
    # fields are scoped to one specific downstream catalog format
    # rather than folded into the core IR. Consumed by
    # DBTExtendedYAMLGenerator (`-g dbt_extended`) only — the plain
    # `dbt` generator (run by default) never touches these.
    #
    # dbt_tags holds only the EXTRA tags beyond the dataset's own name
    # — DBTExtendedYAMLGenerator always appends `name` as the final
    # tag automatically (confirmed identical in both real examples:
    # tags always ended with the dataset's own name), so there's
    # nothing to repeat here that Structifact already knows.
    #
    # dbt_datasource_name, if unset, is derived from `name` (title-
    # cased, underscores to spaces) — also confirmed identical in both
    # real examples (a mechanical transform of the dataset name, not a
    # guess about anything external). Every other field here has no
    # safe default — schema/datasource_project/datasource_extract/
    # data_catalog were identical across both real examples, but that
    # reflects one person's two datasets in one project, not a
    # universal default every Structifact user would want; omitted
    # entirely (never fabricated) when unset, same as pii/comments in
    # ExtendedCatalogCSVGenerator.
    #
    # The dataset-level `description` this maps onto in the generated
    # YAML deliberately reuses the existing `description` field above
    # rather than adding a second one — it's the same concept.
    dbt_schema: Optional[str] = None
    dbt_tags: List[str] = field(default_factory=list)
    dbt_datasource_name: Optional[str] = None
    dbt_datasource_project: Optional[str] = None
    dbt_datasource_extract: Optional[bool] = None
    dbt_data_catalog: Optional[bool] = None

    # Phase 7 remainder — dataset dependency tracking. Names of
    # other Structifact-defined datasets this dataset depends on.
    # NOT the same thing as a computed field's own depends_on (which
    # refers to other fields within the SAME dataset — see
    # FieldSpec.depends_on above); the two live at different nesting
    # levels in the YAML and are unambiguous by context.
    #
    # Declaration only: this says "X must be processed before this
    # dataset can be," and nothing about HOW this dataset obtains
    # X's data. Cross-dataset value resolution, lookup/fallback
    # logic, and SQL generation across dataset boundaries are all
    # explicitly out of scope for this milestone — see
    # structifact/dependencies.py for what this enables (collection-
    # level graph validation, cycle detection, deterministic
    # execution ordering) and what it deliberately does not.
    #
    # Empty list default means any existing dataset with no
    # depends_on declared is completely unaffected — purely additive,
    # same pattern as sources/joins above.
    depends_on: List[str] = field(default_factory=list)


# Backwards compatibility during migration.
#
# TableSpec is intentionally an alias rather than a subclass because
# there is no specialized Table behavior. Existing code importing
# TableSpec should continue to work while DatasetSpec becomes the
# canonical IR name.
TableSpec = DatasetSpec
