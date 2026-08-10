from typing import Optional

from .base import Generator, Artifact
from ..ir import DatasetSpec


class ModelGenerator(Generator):
    """
    Generates a SELECT-based transformation model (closer to a dbt
    model than a DDL statement) that actually computes a dataset's
    `computed` fields, rather than documenting them as a comment the
    way SQLGenerator does.

    Deliberately scoped to a single source, matching the current IR:
    Structifact has no concept yet of joining multiple source tables
    into one dataset (see FUTURE_WORK.md, Transformation Framework,
    "Two Further Gaps Found" — same-table multi-role joins and
    priority-based row dedup are both still undesigned). This
    generator reads from exactly one source table
    (`dataset.source_table`, falling back to `dataset.name` when not
    set) and projects every field — passing non-computed fields
    through as-is, and rendering computed fields' `expression`
    directly, since `expression` is already assumed-valid SQL (same
    trust model as SQLGenerator's comment today, just now actually
    executed instead of only documented).

    Returns None — not an Artifact — for a dataset with no computed
    fields. There is nothing to transform in that case, and emitting
    a no-op `SELECT * FROM x` model would just be clutter with no
    value over the dataset's own DDL. See base.py for the generate()
    contract change this relies on. Not run by default (see
    generators/registry.py) — new generator type, shouldn't silently
    add output for existing users.
    """

    name = "model"

    def generate(self, dataset: DatasetSpec) -> Optional[Artifact]:
        if not any(f.computed for f in dataset.fields):
            return None

        source = dataset.source_table or dataset.name

        select_lines = []

        for f in dataset.fields:
            if f.computed and f.expression:
                select_lines.append(f"    {f.expression} AS {f.name}")
            else:
                select_lines.append(f"    {f.name} AS {f.name}")

        joined_columns = ',\n'.join(select_lines)

        sql = f"""SELECT
{joined_columns}
FROM {source};"""

        return Artifact(
            filename=f"{dataset.name}_model.sql",
            content=sql,
        )
