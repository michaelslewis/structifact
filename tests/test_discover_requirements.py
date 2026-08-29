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


def test_prompt_instructs_excluding_fields_with_no_role_marker():
    # Found via a synthetic document deliberately mimicking a real
    # document's wide/sparse-grid shape: a candidate column with a
    # blank dimension/measure marker (while sibling fields in the
    # same section clearly have one) was consistently included with a
    # guessed role across two separate runs, rather than treated as
    # the join-key/raw-column exclusion signal it actually was.
    prompt = build_requirements_prompt(PROSE_DOC)
    assert "do NOT guess a role and include it" in prompt


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
    # colon inside a field description (e.g. "Account Status: Risk
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
        'dataset: "shipment_header"\n'
        "fields:\n"
        '  - name: "struct_delivhdr_bomusage"\n'
        '    description: "Account Status: Risk Tier"\n'
        "    role: dimension\n"
        '    type: "varchar(2)"\n'
        "unresolved_notes: []\n"
    )

    parsed = parse_requirements_draft(response)

    assert parsed["fields"][0]["description"] == "Account Status: Risk Tier"


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
        '  - name: "struct_delivhdr_statgroup"\n'
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
# source_column / sources / joins extraction and rendering
#
# Closes the gap the prior diagnostic found in examples/workorder_demo:
# the LLM correctly identifies join keys, same-table-multi-role joins,
# and priority dedup rules from a requirements document, but the old
# prompt had no structured slot for any of it -- everything got
# flattened into unresolved_notes as freeform prose (one entry was
# even a stringified Python dict). These tests cover the field-level
# source/source_column shape, the dataset-level sources/joins shape
# (mirroring FieldSpec/SourceRef/JoinSpec/DedupRule in ir.py and
# exactly the YAML shape adapters/yaml.py already loads), and the case
# that should still correctly fall through to unresolved_notes.
# ---------------------------------------------------------------------

# Mirrors the real shape examples/workorder_demo's requirements doc
# describes: the same physical table (partner_role) joined in under
# two different roles, each with its own filter and a priority-based
# dedup rule (prefer is_current, fall back to most recently updated).
SOURCES_JOINS_RESPONSE = """\
dataset: "work_order_source"
fields:
  - name: "work_order_id"
    description: "Work Order ID"
    role: dimension
    type: "varchar(12)"
  - name: "requested_by_name"
    description: "Requested By (Name)"
    role: dimension
    source: "partner_requested_by"
    source_column: "contact_name"
    type: "varchar(60)"
  - name: "billed_to_name"
    description: "Billed To (Name)"
    role: dimension
    source: "partner_billed_to"
    source_column: "contact_name"
    type: "varchar(60)"
source_table: "wo_hdr"
sources:
  - name: "partner_requested_by"
    table: "partner_role"
    filter: "role_code = 'REQ'"
    dedup:
      partition_by: ["wo_id"]
      order_by: ["is_current desc", "updated_at desc"]
  - name: "partner_billed_to"
    table: "partner_role"
    filter: "role_code = 'BILL'"
    dedup:
      partition_by: ["wo_id"]
      order_by: ["is_current desc", "updated_at desc"]
joins:
  - source: "partner_requested_by"
    "on": "wo_hdr.wo_id = partner_requested_by.wo_id"
  - source: "partner_billed_to"
    "on": "wo_hdr.wo_id = partner_billed_to.wo_id"
    type: "inner"
unresolved_notes: []
"""


def test_prompt_instructs_source_column_and_sources_joins():
    prompt = build_requirements_prompt(GRID_DOC)
    assert "source_column" in prompt
    assert "sources" in prompt
    assert "joins" in prompt
    assert "same physical table joined multiple times" in prompt


def test_prompt_warns_about_bare_on_key():
    prompt = build_requirements_prompt(GRID_DOC)
    assert '"on":' in prompt
    assert "parsed as the boolean true" in prompt


def test_parse_preserves_field_source_and_source_column():
    parsed = parse_requirements_draft(SOURCES_JOINS_RESPONSE)
    field = next(f for f in parsed["fields"] if f["name"] == "requested_by_name")
    assert field["source"] == "partner_requested_by"
    assert field["source_column"] == "contact_name"


def test_render_includes_field_source_and_source_column():
    parsed = parse_requirements_draft(SOURCES_JOINS_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")
    assert 'source: "partner_requested_by"' in rendered
    assert 'source_column: "contact_name"' in rendered


def test_render_omits_source_fields_when_absent():
    parsed = parse_requirements_draft(GRID_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")
    assert "source:" not in rendered
    assert "source_column:" not in rendered


def test_render_same_table_multiple_roles_produces_distinct_sources():
    parsed = parse_requirements_draft(SOURCES_JOINS_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    assert 'name: "partner_requested_by"' in rendered
    assert 'name: "partner_billed_to"' in rendered
    # Same physical table, repeated once per role -- not collapsed
    # into one shared entry.
    assert rendered.count('table: "partner_role"') == 2
    assert "role_code = 'REQ'" in rendered
    assert "role_code = 'BILL'" in rendered


def test_render_source_dedup_rule():
    parsed = parse_requirements_draft(SOURCES_JOINS_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    assert "dedup:" in rendered
    assert 'partition_by: ["wo_id"]' in rendered
    assert 'order_by: ["is_current desc", "updated_at desc"]' in rendered


def test_render_joins_use_quoted_on_key():
    parsed = parse_requirements_draft(SOURCES_JOINS_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    assert '"on": "wo_hdr.wo_id = partner_requested_by.wo_id"' in rendered
    assert '"on": "wo_hdr.wo_id = partner_billed_to.wo_id"' in rendered


def test_render_join_type_omitted_when_left_included_when_inner():
    parsed = parse_requirements_draft(SOURCES_JOINS_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    # partner_requested_by's join has no explicit type -> defaults to
    # left, and left is never spelled out (matches the omit-when-
    # default convention elsewhere in this renderer, e.g. `comment`).
    # partner_billed_to's join explicitly said inner -> spelled out.
    # (Fields also have their own unrelated `type:` lines -- e.g.
    # `type: "varchar(12)"` -- so this checks the join-type value
    # specifically, not a bare substring count.)
    assert 'type: "inner"' in rendered
    assert 'type: "left"' not in rendered


def test_render_sources_and_joins_absent_when_not_present():
    # The overwhelming majority of requirements docs describe a single
    # flat table -- confirm no empty 'sources:'/'joins:' clutter shows
    # up in that case (matches GRID_RESPONSE, which has neither key).
    parsed = parse_requirements_draft(GRID_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    assert "sources:" not in rendered
    assert "joins:" not in rendered


def test_render_skips_malformed_source_missing_table():
    parsed = {
        "dataset": "x",
        "fields": [{"name": "f", "type": "string"}],
        "sources": [{"name": "incomplete"}],  # no 'table' -- malformed
        "unresolved_notes": [],
    }
    rendered = render_requirements_draft_yaml(parsed, source_path="x.md")
    assert "incomplete" not in rendered


def test_render_join_falls_back_to_boolean_on_key():
    # Regression for the exact PyYAML 1.1 gotcha this module's own
    # prompt warns the LLM about: a bare `on:` key parses as the
    # Python boolean True, not the string "on". If a real response
    # slips past the prompt's instruction anyway, the join condition
    # must still make it into the rendered draft rather than being
    # silently dropped.
    parsed = {
        "dataset": "x",
        "fields": [{"name": "f", "type": "string"}],
        "sources": [{"name": "customers", "table": "cust_mst"}],
        "joins": [{"source": "customers", True: "x.customer_id = customers.customer_id"}],
        "unresolved_notes": [],
    }
    rendered = render_requirements_draft_yaml(parsed, source_path="x.md")
    assert '"on": "x.customer_id = customers.customer_id"' in rendered


def test_render_converts_dict_shaped_note_to_readable_string():
    # Regression for the exact bug observed in
    # examples/workorder_demo/work_order_source.discovered.yml: a
    # model emitted a nested mapping instead of a plain string for an
    # unresolved_notes entry, and the old code's str() fallback
    # rendered it as a Python repr -- "{'key': 'value'}" -- rather
    # than readable prose.
    parsed = parse_requirements_draft(
        'dataset: "x"\n'
        "fields:\n"
        '  - name: "f"\n'
        '    type: "string"\n'
        "unresolved_notes:\n"
        "  - PARTNER_ROLE must be joined three times: prioritize is_current\n"
    )
    rendered = render_requirements_draft_yaml(parsed, source_path="x.md")

    assert "PARTNER_ROLE must be joined three times: prioritize is_current" in rendered
    # The old repr-shaped artifact must not appear.
    assert "{'PARTNER_ROLE" not in rendered
    assert "{\"PARTNER_ROLE" not in rendered


def test_render_still_falls_through_to_unresolved_notes_for_ambiguous_logic():
    # Part (c): conditional/fallback business logic that genuinely
    # isn't a plain join -- e.g. the FX-rate "use 1.0 only for USD,
    # otherwise leave null" fallback rule -- should still land in
    # unresolved_notes as a plain string, not be forced into
    # sources/joins.
    response = SOURCES_JOINS_RESPONSE.replace(
        "unresolved_notes: []",
        "unresolved_notes:\n"
        '  - "FX conversion: if no rate found and currency is USD, use 1.0; otherwise leave the converted amount null"\n',
    )
    parsed = parse_requirements_draft(response)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    assert len(parsed["unresolved_notes"]) == 1
    assert isinstance(parsed["unresolved_notes"][0], str)
    assert "FX conversion" in rendered
    assert "otherwise leave the converted amount null" in rendered


# ---------------------------------------------------------------------
# source_table -- closes the second-order gap found after the first
# pass: ModelGenerator's primary-source alias is `dataset.source_table
# or dataset.name` (model.py), and the extracted `on:` conditions
# above are written against the primary table's own physical name
# (e.g. "wo_hdr"), which only resolves once source_table is set to
# that same name -- without it, the dataset's logical `name` (e.g.
# "work_order_source") is used instead, and the generated SQL breaks.
# ---------------------------------------------------------------------

def test_prompt_instructs_source_table():
    prompt = build_requirements_prompt(GRID_DOC)
    assert "source_table" in prompt
    assert "primary-table side" in prompt


def test_parse_preserves_source_table():
    parsed = parse_requirements_draft(SOURCES_JOINS_RESPONSE)
    assert parsed["source_table"] == "wo_hdr"


def test_render_includes_source_table():
    parsed = parse_requirements_draft(SOURCES_JOINS_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")
    assert 'source_table: "wo_hdr"' in rendered


def test_render_omits_source_table_when_absent():
    # GRID_RESPONSE has no sources/joins at all, so no source_table
    # either -- a single flat table needs no separate primary alias.
    parsed = parse_requirements_draft(GRID_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")
    assert "source_table:" not in rendered


def test_render_flags_missing_source_table_when_sources_present():
    # The prompt asks for source_table whenever sources/joins are
    # emitted, but that's an instruction, not a guarantee. If a model
    # response has sources/joins with no source_table, the draft must
    # not silently ship something that looks valid (structural
    # validation has no way to catch this -- it's not a schema error)
    # but would generate broken SQL. This does NOT guess a value --
    # it flags the gap in unresolved_notes for a human to fill in.
    response = SOURCES_JOINS_RESPONSE.replace('source_table: "wo_hdr"\n', "")
    parsed = parse_requirements_draft(response)
    assert "source_table" not in parsed  # confirm the fixture edit worked

    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")

    # No source_table *field* was emitted (only the warning note
    # below mentions the key name in prose).
    assert 'source_table: "wo_hdr"' not in rendered
    assert "source_table was not identified" in rendered


def test_render_does_not_flag_missing_source_table_when_no_sources():
    # No sources/joins at all -> no source_table needed -> no warning.
    parsed = parse_requirements_draft(GRID_RESPONSE)
    rendered = render_requirements_draft_yaml(parsed, source_path="REQUIREMENTS.md")
    assert "source_table was not identified" not in rendered


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
