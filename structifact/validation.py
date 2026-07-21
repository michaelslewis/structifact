from .ir import DatasetSpec


SUPPORTED_TYPES = {
    "string",
    "integer",
    "decimal",
    "timestamp",
    "date",
    "boolean",
}


def validate_table(table: DatasetSpec):
    errors = []

    if not table.name:
        errors.append(
            "Table name is required"
        )

    if not table.fields:
        errors.append(
            "Table must contain at least one field"
        )

    field_names = set()

    for field in table.fields:

        if not field.name:
            errors.append(
                "Field name is required"
            )

        elif field.name in field_names:
            errors.append(
                f"Duplicate field name: {field.name}"
            )

        field_names.add(field.name)

        if field.type not in SUPPORTED_TYPES:
            invalid_type = field.raw_type or field.type

            errors.append(
                f"Unsupported type '{invalid_type}' "
                f"for field '{field.name}'"
            )

    if errors:
        raise ValueError(
            "\n".join(errors)
        )