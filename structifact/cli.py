import argparse
import os

from .adapters.registry import load_spec
from .utils import write_file
from .generators.registry import GENERATORS, ALL_GENERATORS
from .validation import validate_table
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
