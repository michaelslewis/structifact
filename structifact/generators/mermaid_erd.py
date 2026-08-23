from .base import Generator, Artifact
from ..ir import DatasetSpec


def _type_display(f) -> str:
    """
    Mirrors docs.py's own _type_display -- not shared across modules,
    matching how sql.py's _sql_type is also generator-local rather
    than a shared helper. Mermaid's erDiagram attribute grammar
    accepts a type token containing parens/commas (confirmed by
    actually rendering "decimal(9,2)" and "string(10)" through mmdc
    before relying on it here), so there's no need to strip precision
    the way a stricter identifier grammar might have forced.
    """
    if f.type == "decimal" and f.precision is not None and f.scale is not None:
        return f"decimal({f.precision},{f.scale})"

    if f.length is not None:
        return f"{f.type}({f.length})"

    return f.type


def _key_marker(field_name: str, pk_columns: set, fk_columns: set) -> str:
    is_pk = field_name in pk_columns
    is_fk = field_name in fk_columns

    if is_pk and is_fk:
        return "PK, FK"

    if is_pk:
        return "PK"

    if is_fk:
        return "FK"

    return ""


class MermaidERDGenerator(Generator):
    """
    Generates a Mermaid `erDiagram` block from a dataset's metadata
    (Step 1 — structifact.com build plan; see scratch/BUILD_PLAN.md and
    docs/DECISION_HISTORY.md's "Two Different Numbering Systems Both
    Called 'Phase'" entry for why the site build plan is numbered in
    "Steps," not "Phases" like this engine's own docs/ROADMAP.md).
    Highest value-per-line
    for the website specifically: a rendered diagram communicates the
    tool in seconds, and GitHub renders Mermaid natively in Markdown
    too.

    Renders this dataset as one entity -- its fields with type,
    PK/FK markers derived from ConstraintSpec (mirrors sql.py's own
    reading of primary_key/foreign_key constraints) -- plus one
    relationship line per foreign_key constraint, connecting to its
    target_table. Like every other generator, this operates on one
    DatasetSpec at a time (see ConstraintSpec's docstring in ir.py:
    "Structifact validates one dataset at a time today and has no
    cross-dataset resolution anywhere in the IR yet"), so a
    referenced target_table appears in the diagram only as a bare
    relationship endpoint, never with its own attribute block --
    this generator has no access to that dataset's FieldSpecs from
    here.

    Relationship cardinality: in Mermaid's erDiagram notation, the
    token adjacent to an entity describes how many of THAT entity
    participate per one instance of the entity on the other end --
    not how many of the other entity it has. That means the FK
    column's own nullability constrains the token next to the
    *target* (how many parents one child row has: exactly one if
    NOT NULL, zero-or-one if nullable), never the token next to this
    dataset itself (how many child rows one parent has) -- nothing
    in a single foreign_key constraint says anything about that, since
    it doesn't declare the FK column unique. So the child-side token
    is always rendered as "zero or many" (`}o`), and only the
    target-side token varies with `FieldSpec.nullable`: NOT NULL
    renders as "exactly one" (`||`), nullable (or the column not
    found on this dataset's fields, which shouldn't normally happen
    but is handled the same way) renders as "zero or one" (`o|`) --
    defaulting to the *weaker* claim when unsure, rather than
    asserting a mandatory relationship the metadata doesn't actually
    establish.

    `depends_on` (DatasetSpec-level) is deliberately NOT rendered as
    a relationship line, even though the build plan's first draft
    grouped it with foreign_key targets. ir.py's own docstring for it
    is explicit that this is "declaration only... nothing about HOW
    this dataset obtains X's data" -- it carries no column mapping
    and no cardinality, unlike a foreign_key constraint. Mermaid's
    erDiagram relationship syntax has no "unspecified" cardinality
    token; every relationship line requires picking one/many and
    optional/mandatory for both sides. Picking one anyway would
    fabricate ER semantics the spec doesn't contain, which runs
    against the same "never fabricate, only render what's present"
    discipline docs.py follows for prose. depends_on is still real
    information worth keeping in the artifact, so it's surfaced as a
    `%%` Mermaid comment instead -- visible to a reader of the
    diagram's source, without asserting a false keyed relationship
    in the rendered picture.
    """

    name = "mermaid_erd"

    def generate(self, dataset: DatasetSpec) -> Artifact:
        lines = ["erDiagram"]

        if dataset.depends_on:
            deps = ", ".join(dataset.depends_on)
            lines.append(f"    %% depends_on: {deps}")

        pk_columns = {
            column
            for c in dataset.constraints
            if c.type == "primary_key"
            for column in c.columns
        }

        fk_constraints = [c for c in dataset.constraints if c.type == "foreign_key"]
        fk_columns = {c.columns[0] for c in fk_constraints}

        fields_by_name = {f.name: f for f in dataset.fields}

        lines.append(f"    {dataset.name} {{")

        for f in dataset.fields:
            marker = _key_marker(f.name, pk_columns, fk_columns)
            attribute = f"        {_type_display(f)} {f.name}"

            if marker:
                attribute += f" {marker}"

            lines.append(attribute)

        lines.append("    }")

        for c in fk_constraints:
            column = c.columns[0]
            fk_field = fields_by_name.get(column)
            target_cardinality = "||" if fk_field is not None and not fk_field.nullable else "o|"

            lines.append(
                f"    {dataset.name} }}o--{target_cardinality} {c.target_table} : \"{column}\""
            )

        return Artifact(
            filename=f"{dataset.name}.mmd",
            content="\n".join(lines) + "\n",
        )
