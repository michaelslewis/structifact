"""
Tests for AI-assisted requirements-document extraction.

Deliberately exercises three structurally different requirements
inputs (mirroring real variation, not just one document shape):

  - "grid": Excel-style per-table field grid with an explicit Logic
    column and freeform notes outside any table (the wholesale-coffee
    example shape).
  - "prose": plain paragraph description, no table at all, including
    a hedge ("we don't have a clean source column for it yet") that
    should NOT get silently turned into a confident field.
  - "terse": bare bullet list with no descriptions and derived fields
    written as inline math shorthand (ctr = clicks / impressions).

FakeLLMClient is fed a hand-written canned YAML response for each
shape, standing in for what a real LLM would return. These tests
verify the prompt-building, parsing, and rendering pipeline handles
all three shapes correctly — they do NOT test the real LLM's
judgment, since FakeLLMClient never calls one.
"""

import io
import os
from unittest import mock

import pytest

from structifact.cli import discover
from structifact.discover import (
    build_requirements_prompt,
    parse_requirements_draft,
    render_requirements_draft_yaml,
)
from structifact.llm import FakeLLMClient


# ---------------------------------------------------------------------
# Stress inputs
# ---------------------------------------------------------------------

GRID_DOC = """\
# Requirements: wholesale_order_source

## ORD_HDR

| Column | Desc | Dim or Meas | Datatype | Length | Logic |
|---|---|---|---|---|---|
| src_ord_hdr_order_id | Order ID | Dim | Varchar | 10 | |
| sign_adjustment | Sign Adjustment | Meas | Integer | | if order_type in ('RET','CRM') then -1 else 1 |

## Notes

Must use a lookup model for FX conversion, joining on currency_code
and order_date. If no rate is found and currency is USD, treat the
rate as 1.0.
"""

GRID_RESPONSE = """\
dataset: wholesale_order_source
fields:
  - name: src_ord_hdr_order_id
    description: Order ID
    role: dimension
    type: varchar(10)
  - name: sign_adjustment
    description: "+1 for standard orders, -1 for returns/credit memos"
    role: measure
    type: integer
    computed: true
    expression: "if order_type in ('RET','CRM') then -1 else 1"
unresolved_notes:
  - "FX conversion requires a lookup joined on currency_code and order_date, with a 1.0 fallback for USD only"
"""

PROSE_DOC = """\
We need a dataset for customer support ticket resolution tracking.
Each row is one ticket. Track the ticket ID, when it was opened and
closed, which agent handled it, and the customer's account tier
(Free, Pro, or Enterprise). We also need a calculated field for
resolution time in hours — closed timestamp minus opened timestamp.
Priority level matters too (Low/Medium/High/Urgent) but we don't have
a clean source column for it yet, it's usually buried in free-text
notes from the agent.
"""

PROSE_RESPONSE = """\
dataset: support_ticket_resolution
fields:
  - name: ticket_id
    description: Unique identifier for the support ticket
    role: dimension
  - name: opened_at
    description: Timestamp the ticket was opened
    role: dimension
  - name: closed_at
    description: Timestamp the ticket was closed
    role: dimension
  - name: agent
    description: Agent who handled the ticket
    role: dimension
  - name: account_tier
    description: "Customer account tier: Free, Pro, or Enterprise"
    role: dimension
  - name: resolution_hours
    description: Resolution time in hours
    role: measure
    computed: true
    expression: "closed timestamp minus opened timestamp"
  - name: priority_level
    description: "Priority: Low, Medium, High, or Urgent"
    role: dimension
    note: "no clean source column identified yet — currently buried in agent free-text notes per the document"
unresolved_notes: []
"""

TERSE_DOC = """\
campaign_performance table:
- campaign_id
- channel (paid_search / social / email / display)
- spend_usd
- impressions
- clicks
- conversions
- ctr = clicks / impressions
- cpa = spend_usd / conversions
"""

TERSE_RESPONSE = """\
dataset: campaign_performance
fields:
  - name: campaign_id
    description: Identifier for the campaign
    role: dimension
  - name: channel
    description: "Marketing channel: paid_search, social, email, or display"
    role: dimension
  - name: spend_usd
    description: Amount spent in USD
    role: measure
  - name: impressions
    description: Number of impressions
    role: measure
  - name: clicks
    description: Number of clicks
    role: measure
  - name: conversions
    description: Number of conversions
    role: measure
  - name: ctr
    description: Click-through rate
    role: measure
    computed: true
    expression: "ctr = clicks / impressions"
  - name: cpa
    description: Cost per acquisition
    role: measure
    computed: true
    expression: "cpa = spend_usd / conversions"
unresolved_notes: []
"""


# ---------------------------------------------------------------------
# build_requirements_prompt
# ---------------------------------------------------------------------

def test_prompt_includes_document_text():
    prompt = build_requirements_prompt(GRID_DOC)
    assert "wholesale_order_source" in prompt
    assert "sign_adjustment" in prompt


def test_prompt_instructs_yaml_only_response():
    prompt = build_requirements_prompt(PROSE_DOC)
    assert "ONLY valid YAML" in prompt
    assert "unresolved_notes" in prompt


def test_prompt_instructs_comment_extraction():
    prompt = build_requirements_prompt(PROSE_DOC)
    assert "comment" in prompt
    assert "Never duplicate the description" in prompt


def test_prompt_instructs_applying_later_override_sections():
    # Found via a real ~500-field document: a later section revising
    # specific already-defined fields' description/comment was being
    # ignored entirely, with the original main-section values used
    # instead. The document's own header text isn't hardcoded here --
    # the instruction describes the general pattern (a later section
    # revising earlier fields, matched by name correspondence even
    # across a differing prefix) so it isn't overfit to one document's
    # exact wording.
    prompt = build_requirements_prompt(PROSE_DOC)
    assert "REPLACE that field's description" in prompt
    assert "not a new set of fields" in prompt


def test_prompt_instructs_double_quoting_every_string():
    # Found via real-world use (a ~500-field document): an unquoted
    # colon inside a field description (e.g. "Credit Management: Risk
    # Category") breaks YAML parsing, since a bare colon starts a new
    # mapping key. Never surfaced in earlier, smaller real examples --
    # none of their descriptions happened to contain a literal colon.
    prompt = build_requirements_prompt(PROSE_DOC)
    assert "Double-quote" in prompt
    assert "colon" in prompt


# ---------------------------------------------------------------------
# parse_requirements_draft — across all three shapes
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "response,expected_dataset,expected_field_count",
    [
        (GRID_RESPONSE, "wholesale_order_source", 2),
        (PROSE_RESPONSE, "support_ticket_resolution", 7),
        (TERSE_RESPONSE, "campaign_performance", 8),
    ],
)
def test_parse_handles_all_three_shapes(response, expected_dataset, expected_field_count):
    parsed = parse_requirements_draft(response)
    assert parsed["dataset"] == expected_dataset
    assert len(parsed["fields"]) == expected_field_count


def test_parse_handles_quoted_value_containing_a_colon():
    # Regression for the real ~500-field-document failure: a properly
    # double-quoted description containing a colon must parse fine --
    # it's specifically an UNQUOTED colon that breaks YAML.
    response = (
        'dataset: "deliveries"\n'
        "fields:\n"
        '  - name: "struct_likp_stlan"\n'
        '    description: "Credit Management: Risk Category"\n'
        "    role: dimension\n"
        '    type: "varchar(2)"\n'
        "unresolved_notes: []\n"
    )

    parsed = parse_requirements_draft(response)

    assert parsed["fields"][0]["description"] == "Credit Management: Risk Category"


def test_parse_flags_computed_field_with_raw_logic():
    parsed = parse_requirements_draft(GRID_RESPONSE)
    computed = [f for f in parsed["fields"] if f.get("computed")]
    assert len(computed) == 1
    assert computed[0]["name"] == "sign_adjustment"
    assert "RET" in computed[0]["expression"]


def test_parse_preserves_uncertainty_note():
    parsed = parse_requirements_draft(PROSE_RESPONSE)
    priority = next(f for f in parsed["fields"] if f["name"] == "priority_level")
    assert "no clean source column" in priority["note"]


def test_parse_preserves_math_shorthand_logic():
    parsed = parse_requirements_draft(TERSE_RESPONSE)
    ctr = next(f for f in parsed["fields"] if f["name"] == "ctr")
    assert ctr["computed"] is True
    assert ctr["expression"] == "ctr = clicks / impressions"


def test_parse_captures_unresolved_join_note():
    parsed = parse_requirements_draft(GRID_RESPONSE)
    assert len(parsed["unresolved_notes"]) == 1
    assert "lookup" in parsed["unresolved_notes"][0]


def test_parse_invalid_yaml_raises():
    with pytest.raises(ValueError, match="not valid YAML"):
        parse_requirements_draft("dataset: [unclosed")


def test_parse_missing_fields_key_raises():
    with pytest.raises(ValueError, match="expected shape"):
        parse_requirements_draft("dataset: foo\n")


def test_parse_defaults_missing_dataset_name():
    parsed = parse_requirements_draft("fields: []\n")
    assert parsed["dataset"] == "unknown_dataset"


def test_parse_handles_null_fields_and_notes():
    # An LLM might emit `fields:` with nothing under it (YAML null)
    # rather than an empty list — don't crash on that.
    parsed = parse_requirements_draft("dataset: foo\nfields:\nunresolved_notes:\n")
    assert parsed["fields"] == []
    assert parsed["unresolved_notes"] == []


# ---------------------------------------------------------------------
# render_requirements_draft_yaml
# ---------------------------------------------------------------------

def test_render_marks_computed_field_and_preserves_logic():
    parsed = parse_requirements_draft(GRID_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")
    assert "computed: true" in rendered
    assert "RET" in rendered


def test_render_includes_comment_when_present():
    parsed = parse_requirements_draft(
        'dataset: "orders"\n'
        "fields:\n"
        '  - name: "struct_likp_stafo"\n'
        '    description: "Statistics Update Grp (DN Hdr)"\n'
        "    role: dimension\n"
        '    comment: "Update Group for Statistics Update"\n'
        '    type: "varchar(6)"\n'
        "unresolved_notes: []\n"
    )
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    assert 'comment: "Update Group for Statistics Update"' in rendered


def test_render_omits_comment_when_absent():
    parsed = parse_requirements_draft(GRID_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    assert "comment:" not in rendered


def test_render_includes_unresolved_notes():
    parsed = parse_requirements_draft(GRID_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")
    assert "unresolved_notes:" in rendered
    assert "lookup" in rendered


def test_render_empty_unresolved_notes_is_valid_yaml_list():
    parsed = parse_requirements_draft(PROSE_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="notes.txt")
    assert "unresolved_notes:\n  []" in rendered


def test_render_skips_fields_with_no_name():
    parsed = {
        "dataset": "x",
        "fields": [{"description": "no name here"}, {"name": "valid_field"}],
        "unresolved_notes": [],
    }
    rendered = render_requirements_draft_yaml(parsed, source_path="x.md")
    assert "valid_field" in rendered
    assert "no name here" not in rendered


# ---------------------------------------------------------------------
# CLI integration — extension dispatch, --ai gate, confirm/decline
# ---------------------------------------------------------------------

def _write(path, content):
    with open(path, "w") as f:
        f.write(content)
    return str(path)


class _Args:
    def __init__(self, spec, output=None, ai=False, yes=False, sample_size=100):
        self.spec = spec
        self.output = output
        self.ai = ai
        self.yes = yes
        self.sample_size = sample_size


def test_md_input_without_ai_makes_no_request_and_writes_nothing(tmp_path):
    spec = _write(tmp_path / "REQUIREMENTS.md", GRID_DOC)
    fake = FakeLLMClient(canned_response=GRID_RESPONSE)
    args = _Args(spec=spec, ai=False)

    discover(args, ai_client=fake)

    assert fake.prompts_received == []
    assert not (tmp_path / "wholesale_order_source.discovered.yml").exists()


def test_md_input_with_ai_declined_makes_no_request(tmp_path, monkeypatch):
    spec = _write(tmp_path / "REQUIREMENTS.md", GRID_DOC)
    fake = FakeLLMClient(canned_response=GRID_RESPONSE)
    args = _Args(spec=spec, ai=True, yes=False)

    monkeypatch.setattr("builtins.input", lambda _: "n")

    discover(args, ai_client=fake)

    assert fake.prompts_received == []
    assert not (tmp_path / "wholesale_order_source.discovered.yml").exists()


def test_md_input_with_ai_and_yes_writes_draft(tmp_path):
    spec = _write(tmp_path / "REQUIREMENTS.md", GRID_DOC)
    fake = FakeLLMClient(canned_response=GRID_RESPONSE)
    output_path = str(tmp_path / "out.yml")
    args = _Args(spec=spec, output=output_path, ai=True, yes=True)

    discover(args, ai_client=fake)

    assert len(fake.prompts_received) == 1
    assert os.path.exists(output_path)

    written = open(output_path).read()
    assert "wholesale_order_source" in written
    assert "computed: true" in written


def test_txt_input_also_dispatches_to_requirements_path(tmp_path):
    spec = _write(tmp_path / "notes.txt", PROSE_DOC)
    fake = FakeLLMClient(canned_response=PROSE_RESPONSE)
    output_path = str(tmp_path / "out.yml")
    args = _Args(spec=spec, output=output_path, ai=True, yes=True)

    discover(args, ai_client=fake)

    written = open(output_path).read()
    assert "support_ticket_resolution" in written
    assert "no clean source column" in written


def test_default_output_path_uses_dataset_name(tmp_path, monkeypatch):
    spec = _write(tmp_path / "REQUIREMENTS.md", GRID_DOC)
    fake = FakeLLMClient(canned_response=GRID_RESPONSE)
    args = _Args(spec=spec, ai=True, yes=True)

    monkeypatch.chdir(tmp_path)
    discover(args, ai_client=fake)

    assert (tmp_path / "wholesale_order_source.discovered.yml").exists()


def test_unparseable_ai_response_does_not_crash_and_writes_nothing(tmp_path):
    spec = _write(tmp_path / "REQUIREMENTS.md", GRID_DOC)
    fake = FakeLLMClient(canned_response="not: valid: yaml: at: all: [")
    output_path = str(tmp_path / "out.yml")
    args = _Args(spec=spec, output=output_path, ai=True, yes=True)

    discover(args, ai_client=fake)

    assert not os.path.exists(output_path)
