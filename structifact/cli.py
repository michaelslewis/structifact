from .parser import load_metadata
from .generators.sql import generate_sql
from .generators.dbt_yaml import generate_dbt_yaml
import os
import sys
import yaml

def main():
    if len(sys.argv) < 2:
        print("Usage: structifact <spec.yml>")
        return

    path = sys.argv[1]

    table = load_metadata(path)  # <-- IR object now

    print("\n--- STRUCTURED VIEW ---\n")
    print(f"Table: {table.name}\n")

    print("Fields:")
    for f in table.fields:
        print(f"- {f.name} ({f.type})")

    sql = generate_sql(table)
    dbt = generate_dbt_yaml(table)

    os.makedirs("output", exist_ok=True)

    sql_path = f"output/{table.name}.sql"
    dbt_path = f"output/{table.name}.yml"

    with open(sql_path, "w") as f:
        f.write(sql)

    with open(dbt_path, "w") as f:
        yaml.dump(dbt, f, sort_keys=False)

    print("\n--- GENERATED ARTIFACTS ---")
    print(f"- {sql_path}")
    print(f"- {dbt_path}")