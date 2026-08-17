import re

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

# Phase 7 — sources/joins milestone. Deliberately small: the
# reference SQL (examples/workorder_demo) only ever uses LEFT joins.
# "inner" is included as the one other obviously-common type worth
# supporting without a design conversation; anything else can be
# added when a real example needs it, same YAGNI reasoning as
# elsewhere in this project.
SUPPORTED_JOIN_TYPES = {
    "left",
    "inner",
}

# Phase 6 v2. min_value/max_value only make sense for numeric types;
# pattern only for string.
NUMERIC_RANGE_TYPES = {"integer", "decimal"}
PATTERN_TYPES = {"string"}


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

        # Range/pattern well-formedness (Phase 6 v2). Unlike the raw
        # SQL fragments elsewhere in the IR (expression, on, filter),
        # a regex pattern can actually be checked for validity here —
        # re.compile either succeeds or it doesn't, no data required.
        # min_value/max_value ordering is likewise checkable without
        # any data. This is the "bad rule -> metadata validation
        # error" half of the v2 contract; "good rule + bad data ->
        # data-quality error" is quality.py's job, not this file's.
        if field.min_value is not None and field.type not in NUMERIC_RANGE_TYPES:
            errors.append(
                f"Field '{field.name}' has min_value but type "
                f"'{field.type}' does not support range validation "
                f"(only integer/decimal fields do)"
            )

        if field.max_value is not None and field.type not in NUMERIC_RANGE_TYPES:
            errors.append(
                f"Field '{field.name}' has max_value but type "
                f"'{field.type}' does not support range validation "
                f"(only integer/decimal fields do)"
            )

        if (
            field.min_value is not None
            and field.max_value is not None
            and field.min_value > field.max_value
        ):
            errors.append(
                f"Field '{field.name}' has min_value ({field.min_value}) "
                f"greater than max_value ({field.max_value})"
            )

        if field.pattern is not None:
            if field.type not in PATTERN_TYPES:
                errors.append(
                    f"Field '{field.name}' has pattern but type "
                    f"'{field.type}' does not support pattern "
                    f"validation (only string fields do)"
                )

            try:
                re.compile(field.pattern)
            except re.error as e:
                errors.append(
                    f"Field '{field.name}' has an invalid pattern "
                    f"'{field.pattern}': {e}"
                )

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

    # Dataset-level depends_on well-formedness (Phase 7 remainder —
    # dataset dependency tracking). NOT the same thing as a computed
    # field's depends_on (which references other fields in the same
    # dataset — see the loop above). Only checks what's determinable
    # from this one dataset in isolation: blank entries, duplicates,
    # self-reference. Whether a referenced dataset actually exists,
    # and whether the resulting graph is cycle-free, are
    # collection-level questions this file can't answer on its own —
    # see dependencies.py, which requires multiple DatasetSpecs.
    seen_dataset_deps = set()
    for dep in table.depends_on:
        if not dep:
            errors.append(
                "depends_on contains a blank entry — remove it"
            )
            continue

        if dep == table.name:
            errors.append(
                f"Dataset '{table.name}' cannot depend on itself"
            )

        if dep in seen_dataset_deps:
            errors.append(
                f"Duplicate entry in depends_on: '{dep}'"
            )
        seen_dataset_deps.add(dep)

    # source_table well-formedness (Phase 7 — ModelGenerator). Only
    # checks that an explicitly-set value isn't blank — None is
    # valid (falls back to dataset name), but an empty string is
    # almost certainly a mistake, not an intentional choice.
    if table.source_table is not None and not table.source_table.strip():
        errors.append(
            "source_table, if set, cannot be blank — omit it "
            "entirely to fall back to the dataset name"
        )

    # source_filter well-formedness (found via real-world use). Same
    # reasoning as source_table above: None means no filter, an empty
    # string is almost certainly a mistake. The filter expression
    # itself is a trusted raw SQL fragment, same as SourceRef.filter —
    # not parsed or semantically checked here.
    if table.source_filter is not None and not table.source_filter.strip():
        errors.append(
            "source_filter, if set, cannot be blank — omit it "
            "entirely if the primary source needs no filter"
        )

    # dbt-target metadata well-formedness (found via real-world use,
    # confirmed by a second independent real example). Same reasoning
    # as source_table/source_filter above for the plain strings; an
    # explicitly-set but blank value is almost certainly a mistake.
    if table.dbt_schema is not None and not table.dbt_schema.strip():
        errors.append(
            "dbt_schema, if set, cannot be blank — omit it entirely "
            "if DBTExtendedYAMLGenerator shouldn't emit a schema"
        )

    if table.dbt_datasource_name is not None and not table.dbt_datasource_name.strip():
        errors.append(
            "dbt_datasource_name, if set, cannot be blank — omit it "
            "entirely to fall back to a title-cased dataset name"
        )

    if table.dbt_datasource_project is not None and not table.dbt_datasource_project.strip():
        errors.append(
            "dbt_datasource_project, if set, cannot be blank — omit "
            "it entirely if DBTExtendedYAMLGenerator shouldn't emit one"
        )

    for tag in table.dbt_tags:
        if not tag.strip():
            errors.append("dbt_tags entries cannot be blank")
            break

    # sources/joins relationship validation (Phase 7 — sources/joins
    # milestone). Structifact doesn't parse or validate the raw SQL
    # fragments (filter, on, order_by) — only the metadata
    # relationships between sources, joins, and fields, which it can
    # actually check meaningfully.
    source_names = set()

    for source in table.sources:
        if not source.name:
            errors.append(
                "Every entry in 'sources' requires a name"
            )
        elif source.name in source_names:
            errors.append(
                f"Duplicate source name: {source.name}"
            )
        source_names.add(source.name)

        if not source.table:
            errors.append(
                f"Source '{source.name}' requires a table"
            )

        if source.dedup is not None and source.aggregate is not None:
            errors.append(
                f"Source '{source.name}' has both a dedup rule and an "
                f"aggregate rule — a source is collapsed to one row "
                f"per key either by picking a single winner (dedup) "
                f"or by aggregating every row in the group "
                f"(aggregate), never both"
            )

        if source.dedup is not None:
            if not source.dedup.partition_by:
                errors.append(
                    f"Source '{source.name}' has a dedup rule with "
                    f"an empty partition_by — a dedup rule requires "
                    f"at least one partition_by column"
                )

            if not source.dedup.order_by:
                errors.append(
                    f"Source '{source.name}' has a dedup rule with "
                    f"an empty order_by — a dedup rule requires at "
                    f"least one order_by entry to break ties"
                )

        if source.aggregate is not None:
            if not source.aggregate.group_by:
                errors.append(
                    f"Source '{source.name}' has an aggregate rule "
                    f"with an empty group_by — an aggregate rule "
                    f"requires at least one group_by column"
                )

            if not source.aggregate.aggregates:
                errors.append(
                    f"Source '{source.name}' has an aggregate rule "
                    f"with no aggregates declared — an aggregate rule "
                    f"requires at least one output column"
                )

            for alias, expression in source.aggregate.aggregates.items():
                if not alias.strip():
                    errors.append(
                        f"Source '{source.name}' has an aggregate "
                        f"rule with a blank output column name"
                    )
                if not expression or not expression.strip():
                    errors.append(
                        f"Source '{source.name}' has an aggregate "
                        f"rule whose '{alias}' entry has a blank "
                        f"expression"
                    )

    for join in table.joins:
        if join.source not in source_names:
            errors.append(
                f"Join references unknown source '{join.source}' — "
                f"it must match a name declared in 'sources'"
            )

        if not join.on:
            errors.append(
                f"Join on source '{join.source}' requires an "
                f"'on' condition"
            )

        if join.type not in SUPPORTED_JOIN_TYPES:
            errors.append(
                f"Unsupported join type '{join.type}' for source "
                f"'{join.source}' — supported types: "
                f"{', '.join(sorted(SUPPORTED_JOIN_TYPES))}"
            )

    for field in table.fields:
        if field.source is not None and field.source not in source_names:
            errors.append(
                f"Field '{field.name}' references unknown source "
                f"'{field.source}' — it must match a name declared "
                f"in 'sources'"
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
