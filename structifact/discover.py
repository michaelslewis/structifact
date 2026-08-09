"""
Deterministic schema discovery from raw sample data.

This is the non-AI half of `structifact discover`: given a raw data
file (currently CSV), infer column names, likely types, nullability,
and a "looks unique in this sample" hint for each column.

This module never touches an LLM and never produces a DatasetSpec
directly. It produces a DiscoveredDataset — a draft — which is
rendered as a YAML file for a human to review. Nothing here is
treated as authoritative metadata; see `render_draft_yaml()`.
"""

import csv
import os
import re
from dataclasses import dataclass, field
from typing import List

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
            lines.append(f"    description: {ai_description}  # AI-suggested, review before trusting")
            lines.append(f"    # {', '.join(hint_parts)}")
        else:
            lines.append(f"    description: TODO  # {', '.join(hint_parts)}")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
