import argparse
import os

from .parser import load_metadata
from .utils import write_file
from .generators.registry import GENERATORS

def generate(args):
    if args.spec.endswith(".xlsx"):
        from .adapters.excel import load_excel

        table = load_excel(args.spec)
    else:
        table = load_metadata(args.spec)

    print("\n--- STRUCTURED VIEW ---\n")
    print(f"Table: {table.name}\n")

    print("Fields:")
    for field in table.fields:
        print(f"- {field.name} ({field.type})")

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