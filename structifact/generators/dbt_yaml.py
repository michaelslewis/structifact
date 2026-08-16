from .base import Generator, Artifact
import yaml
from ..ir import DatasetSpec


class DBTYAMLGenerator(Generator):
    """
    Generates dbt-compatible YAML metadata: name/description per
    column, plus (found via real-world use — a real reference dbt
    YAML had both) `role` and a `source_field` qualifying where each
    column physically comes from.

    `source_field` is built as `<source>.<source_column>` using
    exactly the same resolution `ModelGenerator` already uses to
    qualify SELECT columns (`FieldSpec.source` or the dataset's
    primary source; `FieldSpec.source_column` or the field's own
    name) — not a separately-invented convention. Deliberately does
    NOT attempt to reproduce the reference file's own prefix
    convention on that value: the reference had no textual signal for
    it, and one field in it was internally inconsistent (a dot where
    the real physical column has an underscore) — a sign that
    convention was manually typed, not something to encode as a rule.

    Still does NOT emit dataset-level dbt concepts (`config`/tags,
    `schema`, a dataset `description`, `meta` fields like
    `datasource_name`) — none of these exist anywhere in `DatasetSpec`,
    and adding them from one reference file would be designing an IR
    extension from a single example rather than a demonstrated need.
    See FUTURE_WORK.md.
    """

    name = "dbt"

    def generate(self, table: DatasetSpec) -> Artifact:
        primary = table.source_table or table.name

        columns = []
        for f in table.fields:
            source_alias = f.source or primary
            source_column = f.source_column or f.name

            meta = {}
            if f.role:
                meta["role"] = f.role
            meta["source_field"] = f"{source_alias}.{source_column}"

            columns.append({
                "name": f.name,
                "description": f.description or "",
                "meta": meta,
            })

        data = {
            "version": 2,
            "models": [
                {
                    "name": table.name,
                    "columns": columns,
                }
            ],
        }

        return Artifact(
            filename=f"{table.name}.yml",
            content=yaml.dump(data, sort_keys=False)
        )
