from typing import List, Optional

from .base import Generator, Artifact
from ..ir import DatasetSpec, SourceRef


JOIN_KEYWORDS = {
    "left": "left join",
    "inner": "inner join",
}


def _source_cte(source: SourceRef) -> str:
    """
    Renders one SourceRef as a CTE. Two shapes, matching
    examples/workorder_demo's hand-written reference SQL exactly:

    - No dedup: a plain (optionally filtered) passthrough select.
    - With dedup: a ROW_NUMBER()-ranked inner select, filtered down
      to rn = 1 in the outer select — the priority-based
      deduplication pattern DedupRule represents.
    """
    where_clause = f"\n        where {source.filter}" if source.filter else ""

    if source.dedup is None:
        return (
            f"{source.name} as (\n"
            f"    select *\n"
            f"    from {source.table}"
            f"{where_clause}\n"
            f")"
        )

    partition = ", ".join(source.dedup.partition_by)
    order = ", ".join(source.dedup.order_by)

    return (
        f"{source.name} as (\n"
        f"    select *\n"
        f"    from (\n"
        f"        select *,\n"
        f"            row_number() over (\n"
        f"                partition by {partition}\n"
        f"                order by {order}\n"
        f"            ) as rn\n"
        f"        from {source.table}"
        f"{where_clause}\n"
        f"    ) t\n"
        f"    where rn = 1\n"
        f")"
    )


class ModelGenerator(Generator):
    """
    Generates a SELECT-based transformation model (closer to a dbt
    model than a DDL statement) that actually computes a dataset's
    `computed` fields and, as of the sources/joins milestone, can
    also pull fields in from joined-in sources — rather than
    documenting either as a comment the way SQLGenerator does.

    Two independent capabilities, both additive to the base
    single-source case:

    1. Computed fields (`FieldSpec.computed`/`expression`) — a
       field's `expression` is rendered as-is, unqualified, since it
       may combine multiple columns with arbitrary SQL (not a simple
       column reference Structifact could qualify correctly without
       parsing it).

    2. Sources/joins (`DatasetSpec.sources`/`joins`, `FieldSpec.source`/
       `source_column`) — a dataset can declare additional joinable
       sources, including the same physical table joined in multiple
       times under different roles with independent filters and
       priority-based dedup rules (see SourceRef/JoinSpec/DedupRule
       in ir.py). A field with `source` set is qualified with that
       source's alias; a field with neither is qualified with the
       dataset's own primary source instead of left bare — column
       references are qualified by their source wherever Structifact
       knows what that source is. This is a deliberate SQL-output
       change from this generator's pre-sources/joins behavior (which
       left non-computed fields unqualified) — existing metadata
       stays valid and semantically equivalent, but its generated SQL
       now gains qualification too.

    3. A primary-source filter (`DatasetSpec.source_filter`, found via
       real-world use) — a raw SQL predicate applied to the primary
       source, same trust model as `SourceRef.filter`. When combined
       with any `sources`/`joins`, the primary source is wrapped in
       its own CTE and filtered *before* the join happens, not via a
       trailing `WHERE` — a post-join `WHERE` would be ambiguous
       whenever the filtered column name also exists on a joined-in
       source, which real requirements docs actually do produce, not
       just hypothetically.

    Deliberately NOT yet supported (scoped to a later milestone, not
    snuck into this one): a computed field's `expression` referencing
    a joined-in field by source alias, and conditional-fallback logic
    like the reference example's FX-rate COALESCE pattern.

    Returns None — not an Artifact — for a dataset with no computed
    fields, no sources/joins, no source_filter, AND no field renamed
    away from its physical column via source_column declared. There
    is nothing to transform in that case, and emitting a no-op
    `SELECT * FROM x` model would just be clutter with no value over
    the dataset's own DDL. See base.py for the generate() contract
    change this relies on. Not run by default (see
    generators/registry.py) — new generator type, shouldn't silently
    add output for existing users.

    The `source_column`-alone case (found via real-world use — a real
    single-source dataset with every field renamed from its physical
    column but no filter, join, or computed field at all) was
    originally missed here: `_select_line` already qualified and
    renamed columns correctly whenever this generator ran, but nothing
    checked whether a plain rename alone justified running it, so a
    dataset needing exactly this — and nothing else — silently got
    `None`, which also silently made `execute --materialize`
    unusable for it. See DECISION_HISTORY.md.
    """

    name = "model"

    def generate(self, dataset: DatasetSpec) -> Optional[Artifact]:
        has_computed = any(f.computed for f in dataset.fields)
        has_sources = bool(dataset.sources) or bool(dataset.joins)
        has_filter = bool(dataset.source_filter)
        has_renaming = any(
            f.source_column and f.source_column != f.name
            for f in dataset.fields
        )

        if not has_computed and not has_sources and not has_filter and not has_renaming:
            return None

        primary = dataset.source_table or dataset.name

        if not dataset.sources and not dataset.joins:
            # No joins declared: simpler single-source shape, no CTE
            # wrapper needed. Still qualified (see _select_line). A
            # primary-source filter, if present, is a plain trailing
            # WHERE here -- no join means no risk of the filtered
            # column colliding with a joined-in source's column of
            # the same name (see the CTE-wrapped case below for why
            # that risk is real, not hypothetical, once a join exists).
            select_lines = [
                self._select_line(f, primary, indent="    ")
                for f in dataset.fields
            ]
            joined_columns = ',\n'.join(select_lines)

            where_clause = f"\nwhere {dataset.source_filter}" if dataset.source_filter else ""

            sql = f"""select
{joined_columns}
from {primary}{where_clause};"""

            return Artifact(
                filename=f"{dataset.name}_model.sql",
                content=sql,
            )

        select_lines = [
            self._select_line(f, primary, indent="        ")
            for f in dataset.fields
        ]
        joined_columns = ',\n'.join(select_lines)

        source_ctes = [_source_cte(source) for source in dataset.sources]

        # A primary-source filter can't be a trailing WHERE once a
        # join is involved: found via real-world use -- a real
        # requirements doc had the same column name (a "valid to"
        # date) on both the primary source and a joined-in source, so
        # a post-join WHERE on that column name would be genuinely
        # ambiguous, not just theoretically risky. Wrapping the
        # primary source in its own CTE, filtered before any join
        # happens, avoids the ambiguity and matches how real
        # hand-written SQL for this exact pattern is structured.
        if dataset.source_filter:
            primary_cte = (
                f"{primary} as (\n"
                f"    select *\n"
                f"    from {primary}\n"
                f"    where {dataset.source_filter}\n"
                f")"
            )
            source_ctes.insert(0, primary_cte)

        source_ctes_sql = ",\n\n".join(source_ctes)

        join_lines = []
        for j in dataset.joins:
            keyword = JOIN_KEYWORDS.get(j.type, "left join")
            join_lines.append(f"    {keyword} {j.source}\n        on {j.on}")
        joined_clause = "\n".join(join_lines)

        sql = (
            f"with\n\n"
            f"{source_ctes_sql},\n\n"
            f"final as (\n\n"
            f"    select\n"
            f"{joined_columns}\n\n"
            f"    from {primary}\n"
            f"{joined_clause}\n\n"
            f")\n\n"
            f"select * from final;"
        )

        return Artifact(
            filename=f"{dataset.name}_model.sql",
            content=sql,
        )

    def generate_insert(self, dataset: DatasetSpec) -> Optional[Artifact]:
        """
        Phase 8D v3 — wraps generate()'s SELECT in an
        `INSERT INTO <dataset.name> (<columns>) <select>` statement,
        for materializing this dataset's transformation model into
        its own target table (created separately, via SQLGenerator's
        DDL — this method only produces the write statement, not the
        target's schema).

        Returns None under the same condition generate() does: no
        computed fields and no sources/joins means nothing to
        materialize either.

        Raises ValueError if `dataset.name` (the materialization
        target) is among the relations the underlying SELECT reads
        from — the resolved primary source (`source_table`, or
        `dataset.name` if unset) or any declared source's `table`.
        Materializing into a relation the SELECT itself reads from is
        a self-referential write/read collision, never attempted
        silently. This is a materialization-specific precondition,
        not a general DatasetSpec validation rule — a model reading
        from its own dataset name may be perfectly valid outside of
        materializing it (e.g. read-only use, see 8D v1/v2).
        """
        select_artifact = self.generate(dataset)
        if select_artifact is None:
            return None

        primary = dataset.source_table or dataset.name
        read_relations = {primary} | {source.table for source in dataset.sources}

        if dataset.name in read_relations:
            raise ValueError(
                f"Cannot materialize '{dataset.name}': its model reads "
                f"from a relation of the same name. Set source_table "
                f"(and/or each source's table) to a distinct upstream "
                f"relation to materialize this dataset."
            )

        columns = ", ".join(f.name for f in dataset.fields)
        select_body = select_artifact.content.rstrip().rstrip(";")

        sql = f"INSERT INTO {dataset.name} ({columns})\n{select_body};"

        return Artifact(
            filename=f"{dataset.name}_insert.sql",
            content=sql,
        )

    def _select_line(self, f, primary: str, indent: str) -> str:
        if f.computed and f.expression:
            return f"{indent}{f.expression} as {f.name}"

        source_alias = f.source or primary
        source_column = f.source_column or f.name

        return f"{indent}{source_alias}.{source_column} as {f.name}"
