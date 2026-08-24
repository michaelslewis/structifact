"""
Tests for MermaidERDGenerator (structifact.com build plan, Step 1 —
"Step," not "Phase": see docs/DECISION_HISTORY.md's "Two Different
Numbering Systems Both Called 'Phase'" entry).

Covers: entity block renders fields with type and PK/FK markers
derived from ConstraintSpec; relationship lines are emitted only for
foreign_key constraints, with the target-side cardinality token (not
the child-side one -- see mermaid_erd.py's docstring on how Mermaid's
crow's-foot tokens map to "which entity" they describe) read from the
FK column's own nullable flag; depends_on is rendered as a `%%`
comment rather than a relationship line (see mermaid_erd.py's
docstring for why); the generator is wired into the registry as
optional (not default); and the generated content actually renders as
a valid Mermaid diagram via mmdc.

mmdc only confirms the output is syntactically valid Mermaid -- it
happily renders `}o--||` and `}o--o|` alike, since both are
well-formed relationship lines. It does not know, and cannot check,
which cardinality token is semantically correct for a given nullable
flag; an earlier version of this generator put the nullable-derived
token on the wrong side of the relationship (the child-side token
instead of the target-side one), and the mmdc round-trip test passed
throughout, because a syntactically valid but semantically wrong line
is still syntactically valid. So the relationship-cardinality tests
below assert the exact token string, not just "renders OK" -- that's
the only thing that would have caught it.
"""

import shutil
import subprocess

import pytest

from structifact.ir import DatasetSpec, FieldSpec, ConstraintSpec
from structifact.generators.mermaid_erd import MermaidERDGenerator
from structifact.generators.registry import (
    GENERATORS, OPTIONAL_GENERATORS, ALL_GENERATORS,
)


def _gen():
    return MermaidERDGenerator()


def test_filename_matches_dataset_name():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])
    artifact = _gen().generate(table)
    assert artifact.filename == "customers.mmd"


def test_content_starts_with_erdiagram_keyword():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])
    content = _gen().generate(table).content
    assert content.startswith("erDiagram\n")


def test_entity_block_includes_fields_and_types():
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="id", type="integer"),
            FieldSpec(name="status", type="string"),
        ],
    )

    content = _gen().generate(table).content

    assert "orders {" in content
    assert "integer id" in content
    assert "string status" in content


def test_decimal_field_shows_precision_and_scale():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="amount", type="decimal", precision=9, scale=2)],
    )

    content = _gen().generate(table).content

    assert "decimal(9,2) amount" in content


def test_string_field_shows_length():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="clientid", type="string", length=3)],
    )

    content = _gen().generate(table).content

    assert "string(3) clientid" in content


def test_primary_key_field_gets_pk_marker():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="order_id", type="integer")],
        constraints=[ConstraintSpec(type="primary_key", columns=["order_id"])],
    )

    content = _gen().generate(table).content

    assert "integer order_id PK" in content


def test_foreign_key_field_gets_fk_marker():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="customer_id", type="integer")],
        constraints=[
            ConstraintSpec(
                type="foreign_key",
                columns=["customer_id"],
                target_table="customers",
                target_column="id",
            )
        ],
    )

    content = _gen().generate(table).content

    assert "integer customer_id FK" in content


def test_field_that_is_both_pk_and_fk_gets_combined_marker():
    # A composite scenario -- a column that is simultaneously this
    # dataset's primary key and a foreign key into another dataset.
    table = DatasetSpec(
        name="order_lines",
        fields=[FieldSpec(name="order_id", type="integer")],
        constraints=[
            ConstraintSpec(type="primary_key", columns=["order_id"]),
            ConstraintSpec(
                type="foreign_key",
                columns=["order_id"],
                target_table="orders",
                target_column="id",
            ),
        ],
    )

    content = _gen().generate(table).content

    assert "integer order_id PK, FK" in content


def test_field_with_no_constraint_has_no_key_marker():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="name", type="string")],
    )

    content = _gen().generate(table).content

    lines = [l for l in content.splitlines() if "name" in l]
    assert lines == ["        string name"]


def test_relationship_line_emitted_for_foreign_key():
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="customer_id", type="integer", nullable=False)],
        constraints=[
            ConstraintSpec(
                type="foreign_key",
                columns=["customer_id"],
                target_table="customers",
                target_column="id",
            )
        ],
    )

    content = _gen().generate(table).content

    assert 'orders }o--|| customers : "customer_id"' in content


def test_child_side_token_is_always_zero_or_many_regardless_of_nullable():
    # A single foreign_key constraint never says how many child rows
    # one parent has -- it doesn't declare the FK column unique -- so
    # the token next to THIS dataset (`}o`) must never move, whether
    # the FK column is nullable or not. Only the target-side token may
    # vary (see the two tests below).
    for nullable in (True, False):
        table = DatasetSpec(
            name="orders",
            fields=[FieldSpec(name="customer_id", type="integer", nullable=nullable)],
            constraints=[
                ConstraintSpec(
                    type="foreign_key",
                    columns=["customer_id"],
                    target_table="customers",
                    target_column="id",
                )
            ],
        )

        content = _gen().generate(table).content

        assert "orders }o--" in content, f"nullable={nullable}"


def test_target_side_is_exactly_one_when_fk_column_not_nullable():
    # NOT NULL means every order has a customer -- exactly one parent
    # per child, so the token next to customers (the target/parent)
    # is `||`.
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="customer_id", type="integer", nullable=False)],
        constraints=[
            ConstraintSpec(
                type="foreign_key",
                columns=["customer_id"],
                target_table="customers",
                target_column="id",
            )
        ],
    )

    content = _gen().generate(table).content

    assert 'orders }o--|| customers : "customer_id"' in content


def test_target_side_is_zero_or_one_when_fk_column_nullable():
    # A nullable FK column means an order may have no customer at
    # all -- zero-or-one parent per child, so the token next to
    # customers is `o|`, not `||`.
    table = DatasetSpec(
        name="orders",
        fields=[FieldSpec(name="customer_id", type="integer", nullable=True)],
        constraints=[
            ConstraintSpec(
                type="foreign_key",
                columns=["customer_id"],
                target_table="customers",
                target_column="id",
            )
        ],
    )

    content = _gen().generate(table).content

    assert 'orders }o--o| customers : "customer_id"' in content


def test_no_relationship_line_without_foreign_key_constraint():
    table = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="id", type="integer")],
        constraints=[ConstraintSpec(type="primary_key", columns=["id"])],
    )

    content = _gen().generate(table).content

    assert "--" not in content


def test_depends_on_rendered_as_comment_not_relationship():
    # See mermaid_erd.py's docstring: depends_on is declaration-only
    # (no column mapping, no cardinality), so it must never become a
    # relationship line -- only a `%%` comment.
    table = DatasetSpec(
        name="monthly_summary",
        fields=[FieldSpec(name="id", type="integer")],
        depends_on=["daily_transactions", "reference_rates"],
    )

    content = _gen().generate(table).content

    assert "%% depends_on: daily_transactions, reference_rates" in content
    # No relationship line should have been synthesized from
    # depends_on -- it should appear nowhere except that one comment.
    non_comment_lines = [l for l in content.splitlines() if not l.strip().startswith("%%")]
    assert not any("--" in l for l in non_comment_lines)


def test_depends_on_comment_omitted_when_absent():
    table = DatasetSpec(name="customers", fields=[FieldSpec(name="id", type="integer")])

    content = _gen().generate(table).content

    assert "%%" not in content


def test_mermaid_erd_generator_is_optional_not_default():
    default_names = {g.name for g in GENERATORS}
    optional_names = {g.name for g in OPTIONAL_GENERATORS}
    all_names = {g.name for g in ALL_GENERATORS}

    assert "mermaid_erd" not in default_names
    assert "mermaid_erd" in optional_names
    assert "mermaid_erd" in all_names


@pytest.mark.skipif(
    shutil.which("npx") is None,
    reason="mermaid-cli rendering check requires npx on PATH",
)
def test_generated_diagram_actually_renders_via_mermaid_cli(tmp_path):
    # String assertions above only confirm the text Structifact wrote
    # out. This confirms that text is actually valid Mermaid syntax
    # by running it through the real mermaid-cli renderer (mmdc) --
    # covering PK/FK markers, a relationship line, and a depends_on
    # comment together in one diagram.
    table = DatasetSpec(
        name="orders",
        fields=[
            FieldSpec(name="order_id", type="integer"),
            FieldSpec(name="customer_id", type="integer", nullable=False),
            FieldSpec(name="amount", type="decimal", precision=9, scale=2),
        ],
        constraints=[
            ConstraintSpec(type="primary_key", columns=["order_id"]),
            ConstraintSpec(
                type="foreign_key",
                columns=["customer_id"],
                target_table="customers",
                target_column="id",
            ),
        ],
        depends_on=["reference_rates"],
    )

    artifact = _gen().generate(table)

    mmd_path = tmp_path / artifact.filename
    mmd_path.write_text(artifact.content)
    svg_path = tmp_path / "orders.svg"

    # mmdc renders via a real headless Chromium (puppeteer) under the
    # hood. Chromium's own sandbox needs unprivileged user namespaces,
    # which GitHub Actions' ubuntu-latest runner doesn't provide --
    # confirmed by a real CI failure (`No usable sandbox!`, see
    # DECISION_HISTORY.md) that only showed up in CI, never locally.
    # --no-sandbox is the documented mitigation (https://pptr.dev/troubleshooting)
    # for exactly this "no usable sandbox" environment, and is safe
    # here specifically because the "page" mmdc renders is always this
    # test's own just-generated, non-untrusted Mermaid text -- never
    # arbitrary or attacker-influenced content.
    puppeteer_config_path = tmp_path / "puppeteer-config.json"
    puppeteer_config_path.write_text('{"args": ["--no-sandbox"]}')

    result = subprocess.run(
        [
            "npx", "--yes", "-p", "@mermaid-js/mermaid-cli", "mmdc",
            "-p", str(puppeteer_config_path),
            "-i", str(mmd_path), "-o", str(svg_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        f"mmdc failed to render generated diagram:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert svg_path.exists()
    assert "<svg" in svg_path.read_text()
