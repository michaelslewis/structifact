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

    # Computed-field well-formedness (Phase 7, first minimal step).
    # This only checks that the metadata is internally consistent —
    # it does not (and cannot yet) validate that `expression` is
    # actually valid SQL, since Structifact doesn't execute anything.
    # Requires field_names to be fully populated first, so this runs
    # as its own pass after the loop above rather than inline with
    # it — a field can validly depend_on a field declared later in
    # the same file.
    for field in table.fields:

        if field.computed:
            if not field.expression:
                errors.append(
                    f"Field '{field.name}' is marked computed but has "
                    f"no expression — a computed field requires one"
                )
        elif field.expression:
            errors.append(
                f"Field '{field.name}' has an expression but is not "
                f"marked computed: true — set computed: true, or "
                f"remove the expression if it wasn't intentional"
            )

        if field.depends_on:
            if not field.computed:
                errors.append(
                    f"Field '{field.name}' has depends_on but is not "
                    f"marked computed: true"
                )

            if field.name in field.depends_on:
                errors.append(
                    f"Field '{field.name}' cannot appear in its own "
                    f"depends_on"
                )

            for dep in field.depends_on:
                if dep not in field_names:
                    errors.append(
                        f"Field '{field.name}' depends_on unknown "
                        f"field '{dep}'"
                    )

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

        # `check` constraints are validated by their `expression`,
        # not `columns` — a check expression may reference multiple
        # columns inline (e.g. "start_date < end_date") or none in a
        # form validation.py can easily parse. Requiring `columns`
        # for check would just force awkward/redundant metadata.
        # primary_key / unique / foreign_key still require columns
        # exactly as before.
        if constraint.type != "check":
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

        # foreign_key well-formedness (Phase 1 — ConstraintSpec
        # Foundation, closing the previously-tracked gap). Only
        # single-column foreign keys are supported — see ir.py
        # docstring. target_table/target_column are free-text and
        # not resolved against another dataset.
        if constraint.type == "foreign_key":
            if len(constraint.columns) != 1:
                errors.append(
                    f"foreign_key constraint must reference exactly "
                    f"one column, got {len(constraint.columns)}"
                )

            if not constraint.target_table:
                errors.append(
                    "foreign_key constraint requires target_table"
                )

            if not constraint.target_column:
                errors.append(
                    "foreign_key constraint requires target_column"
                )

        # check well-formedness. Like FieldSpec.expression, this is
        # assumed-valid SQL — Structifact does not parse or validate
        # the SQL itself, only that an expression is present.
        if constraint.type == "check":
            if not constraint.expression:
                errors.append(
                    "check constraint requires an expression"
                )

    if errors:
        raise ValueError(
            "\n".join(errors)
        )
