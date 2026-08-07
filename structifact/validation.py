from .ir import DatasetSpec


SUPPORTED_TYPES = {
    "string",
    "integer",
    "decimal",
    "timestamp",
    "date",
    "boolean",
}

SUPPORTED_ROLES = {
    "dimension",
    "measure",
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

        if field.role is not None and field.role not in SUPPORTED_ROLES:
            errors.append(
                f"Unsupported role '{field.role}' "
                f"for field '{field.name}' "
                f"(must be 'dimension' or 'measure')"
            )

        if field.accepted_values is not None:
            if not field.accepted_values:
                errors.append(
                    f"Field '{field.name}' has an empty "
                    f"accepted_values list — remove it or add values"
                )

            seen_values = set()
            for value in field.accepted_values:
                if value in seen_values:
                    errors.append(
                        f"Duplicate accepted_value '{value}' "
                        f"for field '{field.name}'"
                    )
                seen_values.add(value)

    supported_constraints = {
        "primary_key",
        "unique",
        "foreign_key",
        "check",
    }

    primary_key_count = sum(
        1 for c in table.constraints if c.type == "primary_key"
    )
    if primary_key_count > 1:
        errors.append(
            f"Dataset '{table.name}' has {primary_key_count} "
            f"primary_key constraints — a dataset can have at most one"
        )

    for constraint in table.constraints:

        if constraint.type not in supported_constraints:
            errors.append(
                f"Unsupported constraint type: {constraint.type}"
            )

        if not constraint.columns:
            errors.append(
                f"Constraint '{constraint.type}' requires columns"
            )

        for column in constraint.columns:
            if column not in field_names:
                errors.append(
                    f"Constraint '{constraint.type}' references "
                    f"unknown field '{column}'"
                )

    if errors:
        raise ValueError(
            "\n".join(errors)
        )
