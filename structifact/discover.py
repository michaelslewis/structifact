"""
Deterministic schema discovery from raw sample data, plus
AI-assisted discovery from raw sample data AND from requirements
documents.

This module has three parts:

1. The non-AI half of `structifact discover`: given a raw data file
   (currently CSV), infer column names, likely types, nullability,
   and a "looks unique in this sample" hint for each column.

2. The AI-assisted half of raw-data discovery (`discover --ai`):
   builds a prompt asking an LLM to suggest field descriptions for
   already-inferred columns, and parses the response.

3. Requirements-document extraction (`discover --ai` on a .md/.txt
   file): there is no deterministic half here — a requirements
   document is freeform text, not sampled data rows, so this always
   requires an LLM. Builds a prompt asking an LLM to extract a draft
   field list from the document, and parses/renders the response.

Nothing in this module produces a DatasetSpec directly, and nothing
here is treated as authoritative metadata. Every function that
renders output produces a draft YAML file for a human to review —
see `render_draft_yaml()` and `render_requirements_draft_yaml()`.
"""

import csv
import json
import os
import re
from dataclasses import dataclass, field
from typing import List

import yaml

from .types import infer_type_from_values, is_null_token


_CURRENCY_RE = re.compile(r"^\$?-?[\d,]+\.\d{0,2}$|^\$[\d,]+$")
_DATE_LIKE_RE = re.compile(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}")


@dataclass
class DiscoveredField:
    name: str
    inferred_type: str
    sample_count: int
    null_count: int
    looks_unique: bool
    format_hint: str = ""

    @property
    def nullable(self) -> bool:
        return self.null_count > 0


@dataclass
class DiscoveredDataset:
    name: str
    source_path: str
    row_count: int
    fields: List[DiscoveredField] = field(default_factory=list)


def discover_csv(path: str, sample_size: int = 100) -> DiscoveredDataset:
    """
    Read a raw CSV file (real data rows, not a metadata spec) and
    infer a draft schema from up to `sample_size` rows.
    """
    with open(path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        if reader.fieldnames is None:
            raise ValueError(f"No header row found in {path}")

        columns = {name: [] for name in reader.fieldnames}

        row_count = 0
        for row in reader:
            row_count += 1

            if row_count <= sample_size:
                for name in reader.fieldnames:
                    columns[name].append(row.get(name, ""))

    fields = []
    for name, values in columns.items():
        non_empty = [v.strip() for v in values if not is_null_token(v)]
        inferred_type = infer_type_from_values(values)

        fields.append(
            DiscoveredField(
                name=name,
                inferred_type=inferred_type,
                sample_count=len(values),
                null_count=len(values) - len(non_empty),
                looks_unique=(
                    len(non_empty) > 0
                    and len(set(non_empty)) == len(non_empty)
                ),
                format_hint=_guess_format_hint(inferred_type, non_empty),
            )
        )

    dataset_name = os.path.splitext(os.path.basename(path))[0]

    return DiscoveredDataset(
        name=dataset_name,
        source_path=path,
        row_count=row_count,
        fields=fields,
    )


def _guess_format_hint(inferred_type: str, non_empty_values: list) -> str:
    """
    When a column couldn't be cleanly typed (fell back to "string"),
    give a human a starting guess about *why* rather than leaving
    them to puzzle it out — e.g. "this looks like currency" instead
    of silently saying nothing.
    """
    if inferred_type != "string" or not non_empty_values:
        return ""

    currency_like = sum(1 for v in non_empty_values if _CURRENCY_RE.match(v))
    if currency_like / len(non_empty_values) >= 0.6:
        return (
            "looks like currency values with inconsistent formatting "
            "(e.g. '$' or ',' in some but not all values) — "
            "consider normalizing before treating as decimal"
        )

    date_like = sum(1 for v in non_empty_values if _DATE_LIKE_RE.match(v))
    if date_like / len(non_empty_values) >= 0.6:
        return (
            "looks like dates, but in inconsistent formats — "
            "normalize to one format (e.g. YYYY-MM-DD) before "
            "treating as a date"
        )

    return ""


def build_ai_prompt(discovered: DiscoveredDataset) -> str:
    """
    Build the prompt sent to an LLM asking for suggested field
    descriptions. Only called when a user explicitly opts in via
    `structifact discover --ai` — never automatically.
    """
    lines = [
        "You are helping a data engineer write a metadata description "
        "for a dataset inferred from raw sample data.",
        "For each field below, suggest a concise, one-sentence business "
        "description based on its name and inferred type.",
        "Respond with ONLY 'field_name: description' pairs, one per "
        "line. No other commentary, no markdown formatting.",
        "",
        f"Dataset name: {discovered.name}",
        "",
        "Fields:",
    ]

    for f in discovered.fields:
        lines.append(f"- {f.name} (inferred type: {f.inferred_type})")

    return "\n".join(lines)


def parse_ai_suggestions(raw_text: str) -> dict:
    """
    Parse 'field_name: description' lines from raw LLM output into a
    dict. Malformed lines are silently skipped rather than raising —
    AI output is a suggestion, not a contract Structifact can enforce,
    so this degrades gracefully instead of crashing on an unexpected
    response shape.
    """
    suggestions = {}

    for line in raw_text.splitlines():
        line = line.strip()

        if not line or ":" not in line:
            continue

        name, _, description = line.partition(":")
        name = name.strip().lstrip("-").strip()
        description = description.strip()

        if name and description:
            suggestions[name] = description

    return suggestions


def render_draft_yaml(discovered: DiscoveredDataset, ai_suggestions: dict = None) -> str:
    """
    Render a DiscoveredDataset as a draft YAML file matching
    Structifact's dataset contract — clearly marked as a draft that
    requires human review before it's real metadata.

    ai_suggestions, if provided, maps field name -> AI-suggested
    description. A field with an AI suggestion still shows the
    deterministic hints (blank count, key/format hints) as a comment,
    clearly labeled "AI-suggested, review before trusting" rather
    than silently presented as fact. Fields with no suggestion (or
    when ai_suggestions is None) keep the plain TODO placeholder.
    """
    ai_suggestions = ai_suggestions or {}

    header = [
        "# DRAFT metadata generated by `structifact discover`.",
        "#",
        "# This is a suggestion based on sampled data, not verified",
        "# metadata. Review every field and description below, fix",
        "# anything wrong, then run `structifact validate` on this",
        "# file yourself before treating it as real.",
    ]

    if ai_suggestions:
        header += [
            "#",
            "# Some descriptions below were suggested by an LLM based",
            "# on field names and inferred types only — it has not seen",
            "# your actual data values or business context. Review each",
            "# one; do not assume it is correct.",
        ]

    header += [
        "#",
        f"# Source: {discovered.source_path}",
        f"# Sampled {min(discovered.row_count, 100)} of {discovered.row_count} rows.",
        "",
        "dataset:",
        f"  name: {discovered.name}",
        "  description: TODO — describe this dataset",
        "",
        "fields:",
    ]

    lines = header

    for f in discovered.fields:
        lines.append(f"  - name: {f.name}")
        lines.append(f"    type: {f.inferred_type}")

        hint_parts = [f"sampled {f.sample_count} value(s)"]
        if f.null_count:
            hint_parts.append(f"{f.null_count} blank")
        if f.looks_unique and not f.nullable:
            hint_parts.append("all sampled values unique — possible key")
        if f.inferred_type == "unknown":
            hint_parts.append("could not infer a type — check manually")
        if f.format_hint:
            hint_parts.append(f.format_hint)

        ai_description = ai_suggestions.get(f.name)

        if ai_description:
            lines.append(f"    description: {_yaml_str(ai_description)}  # AI-suggested, review before trusting")
            lines.append(f"    # {', '.join(hint_parts)}")
        else:
            lines.append(f"    description: TODO  # {', '.join(hint_parts)}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------
# Requirements-document extraction
#
# Unlike raw-data discovery, there is no deterministic half here — a
# requirements document is freeform text with no fixed shape (a
# multi-column Excel-style grid, plain prose, a terse bullet list, or
# some mix, often with notes scattered outside any table). Extraction
# always goes through an LLM; `structifact discover` on a .md/.txt
# file requires --ai and prints an explanation if it's omitted.
# ---------------------------------------------------------------------


def extract_text_from_xlsx(path: str) -> str:
    """
    Convert a raw .xlsx requirements document into plain text, for the
    same LLM-extraction path used for .md/.txt (build_requirements_prompt
    below). Dumps every sheet's grid, in workbook order, as one
    " | "-joined line per non-blank row under a "## Sheet: <name>"
    header — the same shape a human would get converting the workbook
    to Markdown by hand, just automated.

    This has no awareness of cell *formatting* — fill color, bold,
    strikethrough. A real requirements workbook can use formatting to
    carry meaning (e.g. a grey fill marking a field as a join-key/
    filter-only, not a real output column) that this plain-text dump
    cannot represent; see DECISION_HISTORY.md for a real case where
    exactly that caused several fields to be silently included in the
    AI's draft that the source document had marked, via color alone,
    as excluded. Formatting-aware extraction is deferred — see
    FUTURE_WORK.md — until a real example justifies the added
    complexity.

    Requires the `excel` extra (pandas, openpyxl) — raises ImportError
    if unavailable, left to the caller to turn into a clear message.
    """
    import pandas as pd

    sheets = pd.read_excel(path, sheet_name=None, header=None)

    blocks = []
    for sheet_name, df in sheets.items():
        rows = []
        for _, row in df.iterrows():
            cells = ["" if pd.isna(v) else str(v).strip() for v in row.tolist()]
            if any(cells):
                rows.append(" | ".join(cells))

        if rows:
            blocks.append(f"## Sheet: {sheet_name}\n\n" + "\n".join(rows))

    return "\n\n".join(blocks)


def build_requirements_prompt(text: str) -> str:
    """
    Build the prompt sent to an LLM asking it to extract a draft
    field list from a raw requirements document. Only called when a
    user explicitly opts in via `structifact discover --ai` on a
    .md/.txt file — never automatically.
    """
    lines = [
        "You are helping a data engineer extract a draft dataset schema "
        "from a raw requirements document. These documents vary widely "
        "in shape: multi-column tables, plain prose, terse bullet "
        "lists, or a mix, often with freeform notes scattered outside "
        "any table.",
        "",
        "For each field you can identify, extract:",
        "  - name",
        "  - description: use the document's own wording if given; "
        "otherwise write a concise, reasonable description from the "
        "field name and surrounding context. Never invent business "
        "meaning that isn't supported by the text.",
        "  - role: dimension or measure",
        "  - comment: optional. Only include this if the document "
        "genuinely gives a SECOND, separate short label for the field "
        "distinct from its description — e.g. a 'short name', "
        "'Tableau name', or 'comments' column that exists alongside a "
        "fuller description column. Never duplicate the description "
        "into this field just to fill it in; omit it entirely when "
        "the document only gives one label per field.",
        "  - type: e.g. varchar(10), decimal(9,2), date, integer — this "
        "MUST use this exact key name 'type' (not 'datatype'), "
        "matching Structifact's real metadata schema, so a "
        "reviewed draft can be loaded directly without renaming "
        "keys. This key is REQUIRED for every field, unlike the "
        "others below — if a type isn't explicitly given or clearly "
        "inferable, use your best reasonable guess (e.g. 'string') "
        "rather than omitting the key, and flag the uncertainty "
        "via the note field instead",
        "  - computed: true if the field's value is derived from other "
        "fields via a formula or conditional expression (a 'Logic' "
        "column, inline math like 'x = y / z', or logic described in "
        "prose) — false or omitted otherwise",
        "  - expression: if computed is true, the exact expression or "
        "logic as written in the document, copied as-is — do NOT "
        "translate it into SQL or any other language. Use the "
        "exact key name 'expression' (not 'computed_logic_raw'), "
        "matching Structifact's real metadata schema.",
        "  - note: optional. Use this ONLY to flag real uncertainty in "
        "your own inference (e.g. 'role guessed from context — no "
        "explicit dimension/measure label in source', or 'no source "
        "column identified for this field yet'). Do not use it to "
        "repeat information already captured in another field.",
        "",
        "Anything you find that does not fit into a single field — join "
        "keys or relationships between tables, cross-field business "
        "rules, lookup or fallback logic, deprioritization or "
        "confirmation-status notes — put into unresolved_notes as a "
        "short plain-language string, one entry per distinct note. Do "
        "not drop information: if it doesn't fit under a field, it "
        "belongs in unresolved_notes instead.",
        "",
        "IMPORTANT — some documents define every field once, then "
        "later contain a SEPARATE section that revises specific "
        "already-defined fields' description and/or comment (for "
        "example a section titled something like 'updated field "
        "names/descriptions', appearing well after the main field "
        "list). If you find such a section: it is not a new set of "
        "fields — match each entry back to the field it revises "
        "(names may use a different prefix or slightly different "
        "spelling than the main definition; match by the part of the "
        "name that clearly corresponds, e.g. shared suffix, not exact "
        "string equality), and REPLACE that field's description "
        "and/or comment with the revised value. Keep everything else "
        "about that field (role, type, computed, expression) from its "
        "original definition. Output exactly one entry per field, "
        "never a duplicate for the same field with its old values "
        "still present alongside the revision.",
        "",
        "Do not invent fields, values, or logic that are not present "
        "or reasonably inferable from the text below.",
        "",
        "Respond with ONLY valid YAML matching this shape — no prose "
        "before or after it, no markdown code fences. Double-quote "
        "EVERY string value, with no exceptions, even ones that look "
        "simple — a real field description or note can contain a "
        "colon (e.g. 'Credit Management: Risk Category'), and an "
        "unquoted colon inside a value breaks YAML parsing:",
        "",
        'dataset: "<inferred dataset name>"',
        "fields:",
        '  - name: "<string>"',
        '    description: "<string>"',
        "    role: dimension | measure",
        '    comment: "<string, optional>"',
        '    type: "<string, optional>"',
        "    computed: <true, only if applicable>",
        '    expression: "<string, only if computed is true>"',
        '    note: "<string, optional>"',
        "unresolved_notes:",
        '  - "<string>"',
        "",
        "--- REQUIREMENTS DOCUMENT ---",
        "",
        text,
    ]

    return "\n".join(lines)


_CODE_FENCE_RE = re.compile(r"^```(?:yaml)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """
    Strip a markdown code fence around the AI's response, if present.

    The prompt explicitly asks for "no markdown code fences", but
    that's an instruction, not a guarantee — real models sometimes
    wrap output in ```yaml ... ``` anyway (observed in practice, not
    hypothetical). yaml.safe_load fails immediately on the leading
    backtick, so stripping a fence when present is more robust than
    failing outright over a purely cosmetic wrapper around otherwise-
    valid YAML.
    """
    stripped = text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    return match.group(1) if match else text


def parse_requirements_draft(raw_text: str) -> dict:
    """
    Parse the LLM's YAML response into a plain dict.

    AI output here is a first-pass suggestion, not a contract
    Structifact can enforce. If the response isn't valid YAML, or
    doesn't have the minimum expected shape (a top-level 'fields'
    list), this raises ValueError with the raw response attached so
    the caller can show the user what actually came back, rather than
    failing confusingly further downstream.
    """
    raw_text = _strip_code_fence(raw_text)

    if raw_text.strip().startswith("```"):
        # _strip_code_fence only strips a fence with a matching close.
        # Still starting with ``` here means the fence never closed —
        # almost always because the response was cut off mid-stream
        # before the model finished, not a formatting quirk to work
        # around. AnthropicLLMClient now also surfaces this directly
        # via stop_reason == "max_tokens" at the source, but this
        # covers any LLMClient implementation that doesn't.
        raise ValueError(
            "AI response appears to have been cut off before "
            "finishing (starts with an unclosed code fence) — this "
            "usually means the output hit the token limit. Try "
            "again, or raise the output token cap if it recurs.\n\n"
            f"Raw response:\n{raw_text}"
        )

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        raise ValueError(
            f"AI response was not valid YAML: {e}\n\n"
            f"Raw response:\n{raw_text}"
        )

    if not isinstance(parsed, dict) or "fields" not in parsed:
        raise ValueError(
            "AI response did not match the expected shape (missing "
            f"top-level 'fields').\n\nRaw response:\n{raw_text}"
        )

    parsed.setdefault("dataset", "unknown_dataset")
    parsed.setdefault("unresolved_notes", [])

    if parsed["fields"] is None:
        parsed["fields"] = []

    if parsed["unresolved_notes"] is None:
        parsed["unresolved_notes"] = []

    return parsed


def _yaml_str(value) -> str:
    """
    Safely render a value as a YAML-parseable double-quoted scalar.

    Python's repr() (used here previously) is NOT safe for this: an
    embedded apostrophe is escaped with a backslash in Python's
    single-quote repr (e.g. "can\\'t"), but YAML single-quoted
    scalars don't support backslash escapes at all — YAML only
    recognizes a DOUBLED single quote ('') as a literal apostrophe.
    Any AI-generated text containing a natural apostrophe (extremely
    common in prose — "customer's", "wasn't specified") silently
    produced invalid YAML. JSON string escaping, by contrast, is a
    valid subset of YAML's double-quoted scalar syntax, so
    json.dumps is the correct tool here, not repr().
    """
    return json.dumps(str(value))


def render_requirements_draft_yaml(parsed: dict, source_path: str) -> str:
    """
    Render the parsed AI extraction as a draft YAML file.

    Everything here comes from a single LLM pass over a requirements
    document — the AI has not seen any actual data, only the
    requirements text. Fields marked `computed` keep their raw logic
    as an opaque string rather than translated SQL, since Structifact
    has no way to represent or generate derived/computed fields yet
    (see ROADMAP.md — Transformation Framework). unresolved_notes
    surfaces everything the AI found but could not structurally place
    (most often join keys/relationships and cross-field business
    rules) so it stays visible instead of silently dropped.
    """
    header = [
        "# DRAFT schema — AI-extracted from a requirements document.",
        "#",
        "# This is a first-pass suggestion from an LLM reading the raw",
        "# document below. It has not been validated, and the AI has",
        "# not seen your actual data — only the requirements text.",
        "#",
        "# Review every field, especially anything marked 'computed':",
        "# Structifact cannot generate SQL for derived fields yet, so",
        "# the raw logic is preserved as text for you to implement by",
        "# hand. Also review everything under unresolved_notes below —",
        "# information the AI found but could not structurally place,",
        "# most often join keys/relationships or cross-field business",
        "# rules.",
        "#",
        f"# Source: {source_path}",
        "",
        "dataset:",
        f"  name: {_yaml_str(parsed.get('dataset', 'unknown_dataset'))}",
        "",
        "fields:",
    ]

    lines = header

    for f in parsed.get("fields") or []:
        if not isinstance(f, dict) or not f.get("name"):
            continue

        lines.append(f"  - name: {_yaml_str(f['name'])}")

        description = f.get("description")
        if description:
            lines.append(f"    description: {_yaml_str(description)}")

        role = f.get("role")
        if role:
            lines.append(f"    role: {_yaml_str(role)}")

        comment = f.get("comment")
        if comment:
            lines.append(f"    comment: {_yaml_str(comment)}")

        field_type = f.get("type")
        if not field_type:
            # load_yaml requires every field to have a type — there's
            # no optional path in the real loader, unlike this
            # draft's prompt (which allows the model to omit it when
            # unsure). Always emit one so the draft is guaranteed
            # loadable regardless of what the model actually did,
            # rather than silently producing an incomplete field that
            # crashes downstream with a KeyError. "string" is the
            # safest/most permissive fallback; the gap is flagged via
            # note so a reviewer knows to fix it, not hidden.
            field_type = "string"
            fallback_note = (
                "AI did not supply a type for this field — defaulted "
                "to 'string', review and correct"
            )
            f = dict(f)
            f["note"] = (
                f"{f['note']}; {fallback_note}" if f.get("note") else fallback_note
            )
        lines.append(f"    type: {_yaml_str(field_type)}")

        if f.get("computed"):
            lines.append("    computed: true")
            logic = f.get("expression", "")
            lines.append(f"    expression: {_yaml_str(logic)}")

        note = f.get("note")
        if note:
            lines.append(f"    note: {_yaml_str(note)}  # AI-flagged uncertainty")

        lines.append("")

    # A note is documented as "a short plain-language string", but
    # models don't always follow that shape exactly (observed in
    # practice: a nested YAML mapping instead of a string). Coerce
    # rather than crash or silently render inconsistent types.
    notes = [n if isinstance(n, str) else str(n) for n in (parsed.get("unresolved_notes") or [])]

    lines.append("unresolved_notes:")
    if notes:
        for n in notes:
            lines.append(f"  - {_yaml_str(n)}")
    else:
        lines.append("  []")

    return "\n".join(lines).rstrip() + "\n"
