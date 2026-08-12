import argparse
import os

from .adapters.registry import load_spec
from .utils import write_file
from .generators.registry import GENERATORS, ALL_GENERATORS
from .validation import validate_table
from .quality import load_data_rows, check_data, resolve_references
from .dependencies import execution_order
from .discover import (
    discover_csv, render_draft_yaml, build_ai_prompt, parse_ai_suggestions,
    build_requirements_prompt, parse_requirements_draft,
    render_requirements_draft_yaml,
)

def validate(args):
    try:
        table = load_spec(args.spec)
        validate_table(table)

    except ValueError as e:
        print("\nValidation failed:\n")
        print(e)
        return

    print(f"✓ Loaded metadata")
    print(f"✓ Parsed {len(table.fields)} fields")
    print(f"✓ Valid schema")
    print(f"✓ No constraint violations")


def _join_rows(rows):
    """Renders a row-number list the way the approved contract reads:
    'appears in data rows 2 and 5', or '2, 5, and 9' for 3+."""
    strs = [str(r) for r in rows]
    if len(strs) == 1:
        return strs[0]
    if len(strs) == 2:
        return f"{strs[0]} and {strs[1]}"
    return ", ".join(strs[:-1]) + f", and {strs[-1]}"


def _format_quality_report(result, fk_target_labels=None):
    """
    Formats a QualityResult into the human-readable report. Kept
    entirely separate from quality.py's check_data() — the core
    checker returns structured data and never prints, so a future
    --format json (not yet built) doesn't require touching the
    checking logic at all.

    fk_target_labels maps a foreign_key source field name to a
    display string like "dq_customers.customer_id", purely for a
    friendlier report line — check_data()/QualityIssue itself has no
    concept of "target_table.target_column" display formatting.
    """
    fk_target_labels = fk_target_labels or {}

    print(f"✓ Loaded data: {result.rows_checked} rows")
    print()

    if result.is_valid:
        print("✓ No data-quality issues found")
        return

    print(f"✗ {len(result.issues)} issue(s) found")

    required = [i for i in result.issues if i.rule == "required"]
    uniqueness = [i for i in result.issues if i.rule == "uniqueness"]
    accepted_values = [i for i in result.issues if i.rule == "accepted_values"]
    range_issues = [i for i in result.issues if i.rule == "range"]
    pattern_issues = [i for i in result.issues if i.rule == "pattern"]
    foreign_key_issues = [i for i in result.issues if i.rule == "foreign_key"]

    if required:
        print("\nRequired-field violations:")
        for issue in required:
            for row in issue.rows:
                print(f"  - {issue.field} is blank at data row {row}")

    if uniqueness:
        print("\nUniqueness violations:")
        for issue in uniqueness:
            print(f"  - {issue.field} '{issue.value}' appears in data rows {_join_rows(issue.rows)}")

    if accepted_values:
        print("\naccepted_values violations:")
        for issue in accepted_values:
            row_label = "data row" if len(issue.rows) == 1 else "data rows"
            print(
                f"  - {issue.field} '{issue.value}' at {row_label} "
                f"{_join_rows(issue.rows)} not in the accepted set"
            )

    if range_issues:
        print("\nRange violations:")
        for issue in range_issues:
            row_label = "data row" if len(issue.rows) == 1 else "data rows"
            print(
                f"  - {issue.field} '{issue.value}' at {row_label} "
                f"{_join_rows(issue.rows)} out of range"
            )

    if pattern_issues:
        print("\nPattern violations:")
        for issue in pattern_issues:
            row_label = "data row" if len(issue.rows) == 1 else "data rows"
            print(
                f"  - {issue.field} '{issue.value}' at {row_label} "
                f"{_join_rows(issue.rows)} does not match the expected pattern"
            )

    if foreign_key_issues:
        print("\nForeign-key violations:")
        for issue in foreign_key_issues:
            target = fk_target_labels.get(issue.field, "the referenced dataset")
            row_label = "data row" if len(issue.rows) == 1 else "data rows"
            print(
                f"  - {issue.field} '{issue.value}' at {row_label} "
                f"{_join_rows(issue.rows)} not found in {target}"
            )


def _parse_ref_args(ref_args):
    """
    Parses --ref alias=schema.yml:data.csv into
    {alias: (schema_path, data_path)}. Raises a clear error on a
    malformed --ref rather than an obscure downstream failure.
    """
    refs = {}
    for raw in ref_args or []:
        if "=" not in raw or ":" not in raw.split("=", 1)[1]:
            raise ValueError(
                f"Invalid --ref '{raw}' — expected format: "
                f"alias=schema.yml:data.csv"
            )
        alias, rest = raw.split("=", 1)
        schema_path, data_path = rest.split(":", 1)
        refs[alias] = (schema_path, data_path)
    return refs


def validate_data(args):
    try:
        table = load_spec(args.spec)
        validate_table(table)

    except ValueError as e:
        print("\nSchema validation failed:\n")
        print(e)
        return

    print(f"✓ Loaded schema: {table.name}")

    try:
        ref_paths = _parse_ref_args(getattr(args, "ref", None))

        loaded_refs = {}
        for alias, (schema_path, data_path) in ref_paths.items():
            ref_schema = load_spec(schema_path)
            validate_table(ref_schema)
            ref_rows = load_data_rows(data_path)
            loaded_refs[alias] = (ref_schema, ref_rows)

        referenced_values = resolve_references(table, loaded_refs)

    except ValueError as e:
        print("\nForeign-key configuration error:\n")
        print(e)
        return

    fk_target_labels = {}
    for constraint in table.constraints:
        if constraint.type == "foreign_key":
            source_column = constraint.columns[0]
            fk_target_labels[source_column] = (
                f"{constraint.target_table}.{constraint.target_column}"
            )

    rows = load_data_rows(args.data)
    result = check_data(table, rows, referenced_values=referenced_values)

    _format_quality_report(result, fk_target_labels=fk_target_labels)


def deps(args):
    """
    Phase 7 remainder — dataset dependency tracking. Loads and
    validates multiple dataset YAML files together, then reports a
    safe processing order (or a clear error: schema validation
    failure, unresolved dependency reference, duplicate dataset
    name, or circular dependency).

    Declaration/ordering only — see dependencies.py's module
    docstring for the explicit scope boundary. This command does not
    resolve or generate anything about HOW one dataset obtains
    another's data.
    """
    tables = []

    for path in args.paths:
        try:
            table = load_spec(path)
            validate_table(table)
        except ValueError as e:
            print(f"\nValidation failed for {path}:\n")
            print(e)
            return
        tables.append(table)

    print(f"✓ Loaded {len(tables)} dataset(s)")

    try:
        order = execution_order(tables)
    except ValueError as e:
        print("\nDependency resolution failed:\n")
        print(e)
        return

    print("\n--- EXECUTION ORDER ---\n")
    for i, name in enumerate(order, start=1):
        print(f"{i}. {name}")


def discover(args, ai_client=None):
    if args.spec.lower().endswith((".md", ".txt")):
        return discover_requirements(args, ai_client=ai_client)

    if not args.spec.lower().endswith(".csv"):
        print(
            "\nstructifact discover currently only supports raw CSV "
            "input, or a requirements document (.md/.txt) with --ai."
        )
        return

    discovered = discover_csv(args.spec, sample_size=args.sample_size)

    sampled = min(discovered.row_count, args.sample_size)

    print(f"✓ Read {discovered.row_count} row(s)")
    print(f"✓ Sampled {sampled} row(s)")
    print(f"✓ Inferred {len(discovered.fields)} column(s)")

    ai_suggestions = None

    if getattr(args, "ai", False):
        if ai_client is None:
            from .llm import AnthropicLLMClient

            try:
                ai_client = AnthropicLLMClient()
            except RuntimeError as e:
                print(f"\n{e}")
                return

        prompt = build_ai_prompt(discovered)
        estimate = ai_client.estimate_cost(prompt)

        print(f"\nAI-assisted field descriptions requested.")
        print(f"Estimate: {estimate.note}")

        proceed = getattr(args, "yes", False)

        if not proceed:
            answer = input("Proceed with this request? [y/N] ").strip().lower()
            proceed = answer == "y"

        if proceed:
            raw = ai_client.suggest_field_descriptions(prompt)
            ai_suggestions = parse_ai_suggestions(raw)
        else:
            print("Skipped — writing deterministic draft only (no AI request made).")

    yaml_content = render_draft_yaml(discovered, ai_suggestions=ai_suggestions)

    output_path = args.output or f"{discovered.name}.discovered.yml"
    write_file(output_path, yaml_content)

    print(f"✓ Wrote draft metadata to {output_path}")
    print("\nThis is a draft, not verified metadata. Review it, fix")
    print("anything wrong, then run:")
    print(f"\n  structifact validate {output_path}\n")


def discover_requirements(args, ai_client=None):
    """
    AI-assisted schema extraction from a raw requirements document
    (.md/.txt). Unlike raw-data discovery, there is no deterministic
    half here — a requirements document has no data rows to sample —
    so this path always requires --ai and does nothing without it.
    """
    if not getattr(args, "ai", False):
        print(
            "\nA requirements document has no data rows to sample, so "
            "structifact can only draft a schema from one with --ai "
            "(this reads the document with an LLM; nothing here is "
            "generated deterministically)."
        )
        return

    with open(args.spec, "r") as f:
        text = f.read()

    if ai_client is None:
        from .llm import AnthropicLLMClient

        try:
            ai_client = AnthropicLLMClient()
        except RuntimeError as e:
            print(f"\n{e}")
            return

    prompt = build_requirements_prompt(text)
    estimate = ai_client.estimate_cost(prompt)

    print(f"\nAI-assisted requirements-document extraction requested.")
    print(f"Estimate: {estimate.note}")

    proceed = getattr(args, "yes", False)

    if not proceed:
        answer = input("Proceed with this request? [y/N] ").strip().lower()
        proceed = answer == "y"

    if not proceed:
        print("Skipped — no AI request made, nothing written.")
        return

    raw = ai_client.complete(prompt)

    try:
        parsed = parse_requirements_draft(raw)
    except ValueError as e:
        print(f"\nCouldn't parse the AI response:\n\n{e}")
        return

    yaml_content = render_requirements_draft_yaml(parsed, source_path=args.spec)

    dataset_name = parsed.get("dataset", "requirements")
    output_path = args.output or f"{dataset_name}.discovered.yml"
    write_file(output_path, yaml_content)

    print(f"✓ Wrote draft metadata to {output_path}")
    print("\nThis is a first-pass AI extraction, not verified metadata.")
    print("Review it — especially any 'computed' fields and everything")
    print("under unresolved_notes — then run:")
    print(f"\n  structifact validate {output_path}\n")


def generate(args):
    try:
        table = load_spec(args.spec)
        validate_table(table)

    except ValueError as e:
        print("\nValidation failed:\n")
        print(e)
        return

    print("\n--- STRUCTURED VIEW ---\n")
    print(f"Table: {table.name}\n")

    print("Fields:")
    for field in table.fields:
        details = field.type

        if field.length:
            details += f"({field.length})"

        if field.precision:
            details += f"({field.precision},{field.scale})"

        print(f"- {field.name} ({details})")

    print("\n--- GENERATED ARTIFACTS ---")

    if args.generators:
        by_name = {g.name: g for g in ALL_GENERATORS}
        requested = [n.strip() for n in args.generators.split(",") if n.strip()]

        unknown = [n for n in requested if n not in by_name]
        if unknown:
            print(f"\nUnknown generator(s): {', '.join(unknown)}")
            print(f"Available: {', '.join(sorted(by_name.keys()))}")
            return

        selected = [by_name[n] for n in requested]
    else:
        selected = GENERATORS

    for gen in selected:
        artifact = gen.generate(table)

        # generate() may return None to mean "nothing to generate
        # for this dataset" (see generators/base.py) — e.g.
        # ModelGenerator for a dataset with no computed fields.
        # Skip writing anything in that case rather than erroring
        # on artifact.filename against a None.
        if artifact is None:
            continue

        path = f"{args.output}/{artifact.filename}"

        write_file(path, artifact.content)

        print(f"- {path}")


def main():
    parser = argparse.ArgumentParser(
        prog="structifact",
        description="Define once. Generate everywhere."
    )

    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser("validate")

    validate_parser.add_argument("spec")

    validate_parser.set_defaults(func=validate)

    validate_data_parser = subparsers.add_parser(
        "validate-data",
        help=(
            "Check real data rows against a dataset's already-declared "
            "metadata rules (nullable, accepted_values, primary_key/"
            "unique). v1: no range/regex validation, no type coercion "
            "— comparisons are on raw CSV string values."
        ),
    )

    validate_data_parser.add_argument("spec")
    validate_data_parser.add_argument("data")

    validate_data_parser.add_argument(
        "--ref", action="append", default=None,
        help=(
            "Reference another dataset for foreign-key checking: "
            "alias=schema.yml:data.csv, where alias matches a "
            "foreign_key constraint's target_table. Repeatable for "
            "multiple references. Required if the schema declares "
            "any foreign_key constraints — running without a needed "
            "--ref is a configuration error, not a silently-skipped "
            "check."
        ),
    )

    validate_data_parser.set_defaults(func=validate_data)

    generate_parser = subparsers.add_parser("generate")

    generate_parser.add_argument("spec")

    generate_parser.add_argument("-o", "--output", default="output")

    generate_parser.add_argument(
        "-g", "--generators", default=None,
        help=(
            "Comma-separated generator names to run instead of the "
            "default set (e.g. 'sql,catalog_extended'). Run without "
            "this flag to see the default generators; an unknown "
            "name lists what's available."
        ),
    )

    generate_parser.set_defaults(func=generate)

    deps_parser = subparsers.add_parser(
        "deps",
        help=(
            "Resolve dataset dependencies across multiple metadata "
            "files and report a safe execution order (or a circular-"
            "dependency error). Declaration/ordering only — does not "
            "resolve or generate anything about how one dataset "
            "obtains another's data."
        ),
    )

    deps_parser.add_argument(
        "paths", nargs="+",
        help="One or more dataset YAML files to resolve together.",
    )

    deps_parser.set_defaults(func=deps)

    discover_parser = subparsers.add_parser("discover")

    discover_parser.add_argument(
        "spec",
        help=(
            "Path to a raw CSV data file, or a requirements document "
            "(.md/.txt) — requirements documents require --ai."
        ),
    )

    discover_parser.add_argument("-o", "--output", default=None)

    discover_parser.add_argument(
        "-n", "--sample-size", type=int, default=100
    )

    discover_parser.add_argument(
        "--ai", action="store_true",
        help=(
            "Ask an LLM to help with discovery: suggests field "
            "descriptions for CSV input, or extracts a draft schema "
            "from a requirements document (.md/.txt). Requires "
            "ANTHROPIC_API_KEY. Off by default — never runs, never "
            "costs anything, unless you pass this explicitly. Shows "
            "a cost estimate and asks for confirmation before making "
            "any request, unless -y is also passed. Required (not "
            "optional) for requirements-document input, since there "
            "is no deterministic way to parse freeform text."
        ),
    )

    discover_parser.add_argument(
        "-y", "--yes", action="store_true",
        help="Skip the confirmation prompt when using --ai.",
    )

    discover_parser.set_defaults(func=discover)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
