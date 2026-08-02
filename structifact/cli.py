import argparse
import os

from .adapters.registry import load_spec
from .utils import write_file
from .generators.registry import GENERATORS, ALL_GENERATORS
from .validation import validate_table
from .discover import discover_csv, render_draft_yaml

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


def discover(args):
    if not args.spec.lower().endswith(".csv"):
        print("\nstructifact discover currently only supports raw CSV input.")
        return

    discovered = discover_csv(args.spec, sample_size=args.sample_size)

    sampled = min(discovered.row_count, args.sample_size)

    print(f"✓ Read {discovered.row_count} row(s)")
    print(f"✓ Sampled {sampled} row(s)")
    print(f"✓ Inferred {len(discovered.fields)} column(s)")

    yaml_content = render_draft_yaml(discovered)

    output_path = args.output or f"{discovered.name}.discovered.yml"
    write_file(output_path, yaml_content)

    print(f"✓ Wrote draft metadata to {output_path}")
    print("\nThis is a draft, not verified metadata. Review it, fix")
    print("anything wrong, then run:")
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

    discover_parser.add_argument("spec")

    discover_parser.add_argument("-o", "--output", default=None)

    discover_parser.add_argument(
        "-n", "--sample-size", type=int, default=100
    )

    discover_parser.set_defaults(func=discover)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
