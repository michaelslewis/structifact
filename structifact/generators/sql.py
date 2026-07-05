from ..ir import TableSpec

def generate_sql(table: TableSpec) -> str:
    cols = []

    for field in table.fields:
        sql_type = "TEXT" if field.type == "string" else field.type.upper()

        cols.append(f"    {field.name} {sql_type}")

    return f"""CREATE TABLE {table.name} (
{",\n".join(cols)}
);"""