from .base import Generator, Artifact
from ..ir import DatasetSpec


SQL_TYPE_MAP = {
    "string": "TEXT",
    "integer": "INTEGER",
    "decimal": "DECIMAL",
    "timestamp": "TIMESTAMP",
    "date": "DATE",
    "boolean": "BOOLEAN",
}


def _sql_type(f) -> str:
    if f.type == "decimal" and f.precision is not None and f.scale is not None:
        return f"DECIMAL({f.precision},{f.scale})"

    return SQL_TYPE_MAP.get(f.type, "TEXT")


class SQLGenerator(Generator):
    """
    Generates a CREATE TABLE DDL statement from a dataset's metadata.

    This is schema declaration, not a transformation query — it does
    not and should not attempt to execute a computed field's
    `expression`. A computed field's expression is documented as a
    SQL comment above its column definition; it is NOT emitted as an
    executable derivation (e.g. no vendor-specific GENERATED ALWAYS
    AS syntax), since that would either be invalid portable SQL or
    lock generated output to one dialect before Structifact has any
    platform-specific integrations (see ROADMAP.md, Phase 8). A
    generator that actually produces a SELECT-based transformation
    model (closer to a dbt model) is a distinct, larger future item,
    not something this generator does.

    Only primary_key and unique constraints are emitted.
    foreign_key and check are accepted by validation as constraint
    types but deliberately NOT emitted here: ConstraintSpec doesn't
    yet carry enough information to generate them correctly (a
    foreign_key needs a target table/column; a check needs its own
    expression). Emitting either now would mean guessing at syntax
    the IR can't actually support yet.
    """

    name = "sql"

    def generate(self, table: DatasetSpec) -> Artifact:
        lines = []

        for f in table.fields:
            if f.computed and f.expression:
                lines.append(f"    -- computed: {f.name} = {f.expression}")

            column_def = f"    {f.name} {_sql_type(f)}"

            if not f.nullable:
                column_def += " NOT NULL"

            lines.append(column_def)

        for c in table.constraints:
            if c.type == "primary_key":
                columns = ", ".join(c.columns)
                lines.append(f"    PRIMARY KEY ({columns})")

            elif c.type == "unique":
                columns = ", ".join(c.columns)
                lines.append(f"    UNIQUE ({columns})")

            # foreign_key / check: deliberately not emitted — see
            # class docstring.

        joined_columns = ',\n'.join(lines)

        sql = f"""CREATE TABLE {table.name} (
{joined_columns}
);"""

        return Artifact(
            filename=f"{table.name}.sql",
            content=sql
        )
