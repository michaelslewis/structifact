import argparse
import os

from .adapters.registry import load_spec
from .utils import write_file
from .generators.registry import GENERATORS
from .validation import validate_table

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

    for gen in GENERATORS:
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

    generate_parser = subparsers.add_parser("generate")

    generate_parser.add_argument("spec")

    generate_parser.add_argument("-o", "--output", default="output")

    generate_parser.set_defaults(func=generate)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()