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

    Deliberately NOT yet supported (scoped to a later milestone, not
    snuck into this one): a computed field's `expression` referencing
    a joined-in field by source alias, and conditional-fallback logic
    like the reference example's FX-rate COALESCE pattern.

    Returns None — not an Artifact — for a dataset with no computed
    fields AND no sources/joins declared. There is nothing to
    transform in that case, and emitting a no-op `SELECT * FROM x`
    model would just be clutter with no value over the dataset's own
    DDL. See base.py for the generate() contract change this relies
    on. Not run by default (see generators/registry.py) — new
    generator type, shouldn't silently add output for existing users.
    """

    name = "model"

    def generate(self, dataset: DatasetSpec) -> Optional[Artifact]:
        has_computed = any(f.computed for f in dataset.fields)
        has_sources = bool(dataset.sources) or bool(dataset.joins)

        if not has_computed and not has_sources:
            return None

        primary = dataset.source_table or dataset.name

        if not dataset.sources and not dataset.joins:
            # No joins declared: simpler single-source shape, no CTE
            # wrapper needed. Still qualified (see _select_line).
            select_lines = [
                self._select_line(f, primary, indent="    ")
                for f in dataset.fields
            ]
            joined_columns = ',\n'.join(select_lines)

            sql = f"""select
{joined_columns}
from {primary};"""

            return Artifact(
                filename=f"{dataset.name}_model.sql",
                content=sql,
            )

        select_lines = [
            self._select_line(f, primary, indent="        ")
            for f in dataset.fields
        ]
        joined_columns = ',\n'.join(select_lines)

        source_ctes = ",\n\n".join(
            _source_cte(source) for source in dataset.sources
        )

        join_lines = []
        for j in dataset.joins:
            keyword = JOIN_KEYWORDS.get(j.type, "left join")
            join_lines.append(f"    {keyword} {j.source}\n        on {j.on}")
        joined_clause = "\n".join(join_lines)

        sql = (
            f"with\n\n"
            f"{source_ctes},\n\n"
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

    def _select_line(self, f, primary: str, indent: str) -> str:
        if f.computed and f.expression:
            return f"{indent}{f.expression} as {f.name}"

        source_alias = f.source or primary
        source_column = f.source_column or f.name

        return f"{indent}{source_alias}.{source_column} as {f.name}"
