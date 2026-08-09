from .base import Generator, Artifact
from ..ir import DatasetSpec


def _type_display(f) -> str:
    """
    Render a field's normalized type together with its length or
    precision/scale when present, e.g. "decimal(9,2)" or
    "varchar(10)" — mirrors the shape catalog.py's _length_display
    conveys separately, combined into one string for readable prose.
    """
    if f.type == "decimal" and f.precision is not None and f.scale is not None:
        return f"decimal({f.precision},{f.scale})"

    if f.length is not None:
        return f"{f.type}({f.length})"

    return f.type


class DocsGenerator(Generator):
    """
    Generates human-readable Markdown documentation from a dataset's
    metadata (Phase 5 — Documentation Generation).

    Renders only what's actually present on the metadata. Never
    fabricates or infers a value a field doesn't have — a field with
    no role, no accepted_values, etc. simply omits that line rather
    than guessing or showing a placeholder.

    Deliberately does NOT include a computed/derived-logic section:
    FieldSpec has no field for representing derived/computed logic
    yet (see ROADMAP.md, Phase 7 — Transformation Framework). Adding
    one here would mean inventing metadata that doesn't exist in the
    IR, which is exactly what this generator is designed not to do.
    """

    name = "docs"

    def generate(self, table: DatasetSpec) -> Artifact:
        lines = [f"# {table.name}", ""]

        if table.description:
            lines.append(table.description)
            lines.append("")

        lines.append("## Fields")
        lines.append("")

        for f in table.fields:
            lines.append(f"### {f.name}")
            lines.append("")

            lines.append(f"- **Type:** {_type_display(f)}")

            if f.raw_type:
                lines.append(f"- **Declared as:** {f.raw_type}")

            if f.role:
                lines.append(f"- **Role:** {f.role}")

            lines.append(f"- **Nullable:** {'Yes' if f.nullable else 'No'}")

            if f.accepted_values:
                values = ", ".join(f"`{v}`" for v in f.accepted_values)
                lines.append(f"- **Accepted values:** {values}")

            if f.description:
                lines.append("")
                lines.append(f.description)

            lines.append("")

        if table.constraints:
            lines.append("## Constraints")
            lines.append("")

            for c in table.constraints:
                columns = ", ".join(c.columns)
                lines.append(f"- **{c.type}**: {columns}")

            lines.append("")

        return Artifact(
            filename=f"{table.name}.md",
            content="\n".join(lines).rstrip() + "\n",
        )
