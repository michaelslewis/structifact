import argparse

from .parser import load_metadata
from .generators.sql import generate_sql
from .generators.dbt_yaml import generate_dbt_yaml
from .utils import write_file


def generate(args):
    table = load_metadata(args.spec)

    print("\n--- STRUCTURED VIEW ---\n")
    print(f"Table: {table.name}\n")

    print("Fields:")
    for field in table.fields:
        print(f"- {field.name} ({field.type})")

    sql = generate_sql(table)
    dbt = generate_dbt_yaml(table)

    write_file(f"{args.output}/{table.name}.sql", sql)
    write_file(f"{args.output}/{table.name}.yml", dbt)

    print("\n--- GENERATED ARTIFACTS ---")
    print(f"- {args.output}/{table.name}.sql")
    print(f"- {args.output}/{table.name}.yml")


def main():
    parser = argparse.ArgumentParser(
        prog="structifact",
        description="Define once. Generate everywhere."
    )

    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate artifacts from a specification"
    )

    generate_parser.add_argument(
        "spec",
        help="Input specification file"
    )

    generate_parser.add_argument(
        "-o",
        "--output",
        default="output",
        help="Output directory"
    )

    generate_parser.set_defaults(func=generate)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()