"""
Tests for the orphaned-source warning: a declared, joined SourceRef
that never actually contributes a value -- found via a real
investigation re-examining the workorder requirements-document
source-attribution bug (three WO_LINE fields silently defaulted to
the primary source instead of `source: work_order_line`, which was
declared and joined but never referenced by any field). See
docs/DECISION_HISTORY.md for the full investigation, including two
real false positives found and excluded (source_table ==
source.name; a source used only inside a computed expression) and one
real refinement needed to avoid silently un-catching the actual bug
(a join's `on` condition naming another source is plumbing for that
OTHER join, not evidence the named source contributes a value).

Same warning-only posture and infrastructure as the join-risk check
in test_model_pick_one_order_by.py: validate_table() returns a list
of warnings, never raises for this.
"""

import pytest

from structifact.ir import DatasetSpec, FieldSpec, SourceRef, JoinSpec, DedupRule
from structifact.validation import validate_table


def test_reproduced_workorder_shape_warns():
    # Reproduces the actual bug shape: `work_order_line` is declared
    # and joined, and is even referenced as a qualifier in a
    # *different* join's `on` condition (price_condition's join needs
    # work_order_line.rate_code) -- but no field ever sets
    # `source: work_order_line`. This is exactly the case that a
    # naive "does this alias appear anywhere as a qualifier" check
    # would miss (see the investigation) -- `price_condition` must
    # NOT be flagged (it IS legitimately used, via `labor_rate`
    # below), only `work_order_line` should be.
    table = DatasetSpec(
        name="work_order_source",
        source_table="WO_HDR",
        fields=[
            FieldSpec(name="work_order_id", type="string"),
            # Bug reproduced: these should have source="work_order_line"
            # but don't -- silently defaults to the primary source.
            FieldSpec(name="line_id", type="string", source_column="src_wo_line_line_id"),
            FieldSpec(name="labor_hours", type="decimal", source_column="src_wo_line_labor_hours"),
            # Correctly attributed, for contrast.
            FieldSpec(name="labor_rate", type="decimal", source="price_condition"),
        ],
        sources=[
            SourceRef(name="work_order_line", table="WO_LINE"),
            SourceRef(name="price_condition", table="PRICE_COND"),
        ],
        joins=[
            JoinSpec(source="work_order_line", on="WO_HDR.wo_id = work_order_line.wo_id"),
            JoinSpec(
                source="price_condition",
                on="work_order_line.rate_code = price_condition.rate_code",
            ),
        ],
    )

    warnings = validate_table(table)

    orphaned_warnings = [w for w in warnings if "Orphaned source" in w]
    assert len(orphaned_warnings) == 1
    assert "work_order_line" in orphaned_warnings[0]
    assert "price_condition" not in orphaned_warnings[0]


def test_source_table_equals_source_name_does_not_warn():
    # The documented source_table == sources[0].name trick (see
    # examples/value_experiment/order_status_resolved.yml) --
    # deliberately constructed here WITH an explicit join too (unusual
    # in practice; real examples using this trick have no `joins:` at
    # all, which already skips them via the "must be joined" gate) so
    # this test exercises the source_table exclusion itself, not just
    # the joined-only gate.
    table = DatasetSpec(
        name="claims",
        source_table="candidates",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[
            SourceRef(
                name="candidates", table="claim_candidates",
                dedup=DedupRule(partition_by=["claim_id"], order_by=["effective_date desc"]),
            ),
        ],
        joins=[
            JoinSpec(source="candidates", on="candidates.claim_id = candidates.claim_id"),
        ],
    )

    warnings = validate_table(table)

    assert not [w for w in warnings if "Orphaned source" in w]


def test_qualified_expression_usage_does_not_warn():
    # The fx_rate case from tonight's own reviewed workorder YAML:
    # a source used only inside a computed expression's qualified
    # reference (fx_rate.rate_to_usd), never via FieldSpec.source.
    table = DatasetSpec(
        name="work_order_source",
        source_table="WO_HDR",
        fields=[
            FieldSpec(name="work_order_id", type="string"),
            FieldSpec(
                name="resolved_fx_rate", type="decimal", computed=True,
                expression="COALESCE(fx_rate.rate_to_usd, 1.0)",
            ),
        ],
        sources=[SourceRef(name="fx_rate", table="fx_rate_lookup")],
        joins=[
            JoinSpec(
                source="fx_rate",
                on="WO_HDR.currency_code = fx_rate.currency_code",
            ),
        ],
    )

    warnings = validate_table(table)

    assert not [w for w in warnings if "Orphaned source" in w]


def test_source_referenced_only_in_a_joins_on_condition_still_warns():
    # Per this check's own definition (and the investigation that
    # found it necessary): joins.on is plumbing establishing a
    # relationship between sources, not evidence a source contributes
    # a value -- a source visible ONLY through an `on` condition (its
    # own, or another join's) must still warn. This is the exact
    # mechanism that made `work_order_line` invisible to an earlier,
    # broader draft of this check (see
    # test_reproduced_workorder_shape_warns and
    # docs/DECISION_HISTORY.md) -- isolated here on its own, with a
    # single join and nothing else in the dataset that could count as
    # usage.
    table = DatasetSpec(
        name="claims",
        source_table="CLAIM_HDR",
        fields=[FieldSpec(name="claim_id", type="string")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(source="policy_status", on="CLAIM_HDR.policy_id = policy_status.policy_id"),
        ],
    )

    warnings = validate_table(table)

    orphaned_warnings = [w for w in warnings if "Orphaned source" in w]
    assert len(orphaned_warnings) == 1
    assert "policy_status" in orphaned_warnings[0]


def test_orphaned_source_warning_surfaces_alongside_a_hard_error():
    # Same ValidationError.warnings mechanism as the join-risk check:
    # a real error elsewhere must not suppress this warning.
    table = DatasetSpec(
        name="claims",
        source_table="CLAIM_HDR",
        fields=[FieldSpec(name="claim_id", type="bogus_type")],
        sources=[SourceRef(name="policy_status", table="policy_status_history")],
        joins=[
            JoinSpec(source="policy_status", on="CLAIM_HDR.policy_id = policy_status.policy_id"),
        ],
    )

    with pytest.raises(ValueError) as exc_info:
        validate_table(table)

    assert "Unsupported type 'bogus_type'" in str(exc_info.value)

    error_warnings = getattr(exc_info.value, "warnings", [])
    orphaned_warnings = [w for w in error_warnings if "Orphaned source" in w]
    assert len(orphaned_warnings) == 1
    assert "policy_status" in orphaned_warnings[0]
