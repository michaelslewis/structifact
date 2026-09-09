"""
Tests for SQLGenerator's nullable/constraint/computed-field handling,
and the yaml.py fix that makes `nullable:` actually reach the IR.

Covers the golden cases:
  nullable: false -> NOT NULL
  nullable: true (or unset) -> no NOT NULL
  primary_key constraint -> PRIMARY KEY (...)
  unique constraint -> UNIQUE (...)
  computed field with expression -> SQL comment, no executable syntax

foreign_key / check constraint emission is covered separately in
tests/test_constraint_fk_check.py, alongside the ConstraintSpec
validation that makes emitting them meaningful (target_table/
target_column for foreign_key, expression for check). They used to
be documented here as "not emitted" — that was correct at the time,
but is no longer true as of the ConstraintSpec foreign_key/check
work, so those two cases moved rather than staying here stale.
"""

import os
import tempfile

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.generators.sql import SQLGenerator
from structifact.adapters.yaml import load_yaml


def _gen():
    return SQLGenerator()


def _write_yaml(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".yml")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------
# nullable -> NOT NULL
# ---------------------------------------------------------------------

def test_nullable_false_emits_not_null():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="integer", nullable=False)],
    )
    sql = _gen().generate(table).content
    assert '"order_id" INTEGER NOT NULL' in sql


def test_nullable_true_omits_not_null():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="notes", type="string", nullable=True)],
    )
    sql = _gen().generate(table).content
    assert "NOT NULL" not in sql


def test_nullable_default_omits_not_null():
    # nullable defaults to True on FieldSpec when not specified at all
    table = DatasetSpec(name="orders", fields=[FieldSpec(name="notes", type="string")])
    sql = _gen().generate(table).content
    assert "NOT NULL" not in sql


def test_yaml_adapter_parses_nullable_false():
    path = _write_yaml("""
dataset:
  name: orders
fields:
  - name: order_id
    type: integer
    nullable: false
""")
    table = load_yaml(path)
    assert table.fields[0].nullable is False


def test_yaml_adapter_defaults_nullable_true_when_absent():
    path = _write_yaml("""
dataset:
  name: orders
fields:
  - name: order_id
    type: integer
""")
    table = load_yaml(path)
    assert table.fields[0].nullable is True


def test_yaml_nullable_reaches_generated_sql_end_to_end():
    # The actual bug this fixes: nullable: false in YAML previously
    # never reached FieldSpec at all, so SQLGenerator honoring it
    # would have been silently ineffective. This proves the full
    # path YAML -> IR -> SQL works.
    path = _write_yaml("""
dataset:
  name: orders
fields:
  - name: order_id
    type: integer
    nullable: false
""")
    table = load_yaml(path)
    sql = _gen().generate(table).content
    assert '"order_id" INTEGER NOT NULL' in sql


# ---------------------------------------------------------------------
# primary_key / unique constraints
# ---------------------------------------------------------------------

def test_primary_key_constraint_emitted():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="integer")],
        constraints=[ConstraintSpec(type="primary_key", columns=["order_id"])],
    )
    sql = _gen().generate(table).content
    assert 'PRIMARY KEY ("order_id")' in sql


def test_unique_constraint_emitted():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="email", type="string")],
        constraints=[ConstraintSpec(type="unique", columns=["email"])],
    )
    sql = _gen().generate(table).content
    assert 'UNIQUE ("email")' in sql


def test_composite_primary_key_emitted():
    table = DatasetSpec(
        name="order_lines",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(name="line_id", type="integer"),
        ],
        constraints=[ConstraintSpec(type="primary_key", columns=["order_id", "line_id"])],
    )
    sql = _gen().generate(table).content
    assert 'PRIMARY KEY ("order_id", "line_id")' in sql


# ---------------------------------------------------------------------
# computed field -> comment annotation only
# ---------------------------------------------------------------------

def test_computed_field_gets_comment_annotation():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="qty", type="integer"),
            FieldSpec(name="unit_price", type="decimal"),
            FieldSpec(
                name="gross_amount", type="decimal", computed=True,
                expression="qty * unit_price",
            ),
        ],
    )
    sql = _gen().generate(table).content
    assert "-- computed: gross_amount = qty * unit_price" in sql
    assert '"gross_amount" DECIMAL' in sql


def test_computed_field_produces_valid_ddl_shape():
    # The comment line must not break comma placement between real
    # column definitions — verify the DDL still parses as a sane
    # comma-separated column list once comments are stripped.
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="qty", type="integer"),
            FieldSpec(name="unit_price", type="decimal"),
            FieldSpec(
                name="gross_amount", type="decimal", computed=True,
                expression="qty * unit_price",
            ),
        ],
    )
    sql = _gen().generate(table).content

    # Strip SQL line comments the way a real parser would, then
    # check the remaining column list is well-formed (no stray
    # double-commas, no missing comma between real columns).
    stripped_lines = []
    for line in sql.splitlines():
        code_part = line.split("--")[0].rstrip()
        if code_part.strip():
            stripped_lines.append(code_part)

    stripped = "\n".join(stripped_lines)
    assert ",," not in stripped.replace(" ", "").replace("\n", "")
    assert '"qty" INTEGER' in stripped
    assert '"unit_price" DECIMAL' in stripped
    assert '"gross_amount" DECIMAL' in stripped


def test_non_computed_field_no_comment():
    table = DatasetSpec(name="orders", fields=[FieldSpec(name="qty", type="integer")])
    sql = _gen().generate(table).content
    assert "-- computed" not in sql


def test_computed_true_without_expression_gets_no_comment():
    # Defensive: a computed field with no expression (which
    # validation would normally reject before generation runs)
    # shouldn't crash generation or emit a broken comment.
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="x", type="integer", computed=True)],
    )
    sql = _gen().generate(table).content
    assert "-- computed" not in sql
    assert '"x" INTEGER' in sql


# ---------------------------------------------------------------------
# Identifier quoting (Issue #1 — a dataset/field/constraint-reference
# name that isn't a valid unquoted SQL identifier, e.g. one with
# spaces, previously produced invalid, unrunnable SQL with no warning
# anywhere in the pipeline). See structifact/sql_identifiers.py for
# the quoting rule itself; these tests confirm SQLGenerator actually
# applies it everywhere an identifier is emitted. Deliberately scoped
# to SQLGenerator + the two executors' load_rows (see
# tests/test_executors.py) — ModelGenerator is untouched by this fix,
# a separate, undecided design question (see DECISION_HISTORY.md).
# ---------------------------------------------------------------------

def test_dataset_name_with_spaces_is_quoted():
    # The real, reported bug: dataset.name: "Vendor Data" (exactly the
    # AI-inferred name from output/Vendors.discovered.yml, the real
    # file Issue #1 was reproduced against) previously generated
    # `CREATE TABLE Vendor Data (...)` -- invalid SQL, reported as a
    # success by `structifact generate` regardless.
    table = DatasetSpec(
        name="Vendor Data",
        fields=[FieldSpec(name="vendor_id", type="integer")],
    )
    sql = _gen().generate(table).content
    assert 'CREATE TABLE "Vendor Data" (' in sql
    assert "CREATE TABLE Vendor Data (" not in sql


def test_already_safe_names_are_quoted_but_functionally_unaffected():
    # Regression: an ordinary, already-safe name (lowercase, no
    # spaces, not a reserved word) is quoted unconditionally too --
    # deliberately not a "quote only if needed" heuristic (see
    # sql_identifiers.py) -- but this must not change what the DDL
    # actually declares, only its literal spelling. Every column,
    # the PRIMARY KEY reference, and the table name itself keep their
    # exact names, just wrapped in double quotes.
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(name="customer_id", type="integer"),
        ],
        constraints=[ConstraintSpec(type="primary_key", columns=["order_id"])],
    )
    sql = _gen().generate(table).content
    assert sql == (
        'CREATE TABLE "orders" (\n'
        '    "order_id" INTEGER,\n'
        '    "customer_id" INTEGER,\n'
        '    PRIMARY KEY ("order_id")\n'
        ');'
    )


def test_dataset_name_with_embedded_double_quote_is_escaped():
    # ANSI SQL rule: an embedded double quote inside a quoted
    # identifier must be doubled, or the generated SQL is broken in a
    # different way (the quote would prematurely close the
    # identifier). Deliberately an unusual but real-shaped name (a
    # human-authored dataset title containing a quoted term), not a
    # contrived string -- confirms sql_identifiers.quote_identifier()
    # actually reaches this generator's output correctly escaped, not
    # just naively wrapped.
    table = DatasetSpec(
        name='Bob\'s "Special" Orders',
        fields=[FieldSpec(name="order_id", type="integer")],
    )
    sql = _gen().generate(table).content
    assert 'CREATE TABLE "Bob\'s ""Special"" Orders" (' in sql