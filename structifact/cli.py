import argparse
import os
import sys

from .adapters.registry import load_spec
from .utils import write_file
from .generators.registry import GENERATORS, ALL_GENERATORS
from .validation import validate_table
from .quality import load_data_rows, check_data, resolve_references
from .reconciliation import (
    load_reconciliation_mapping, validate_mapping, reconcile_data,
)
from .dependencies import execution_order, impacted_by
from .executors.registry import EXECUTORS
from .generators.sql import SQLGenerator
from .generators.model import ModelGenerator
from .discover import (
    discover_csv, render_draft_yaml, build_ai_prompt, parse_ai_suggestions,
    build_requirements_prompt, parse_requirements_draft,
    render_requirements_draft_yaml, extract_text_from_xlsx,
)

def validate(args):
    try:
        table = load_spec(args.spec)
        validate_table(table)

    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ValueError as e:
        print("\nValidation failed:\n")
        print(e)
        return False

    print(f"✓ Loaded metadata")
    print(f"✓ Parsed {len(table.fields)} fields")
    print(f"✓ Valid schema")
    print(f"✓ No constraint violations")
    return True


def _join_rows(rows):
    """Renders a row-number list the way the approved contract reads:
    'appears in data rows 2 and 5', or '2, 5, and 9' for 3+."""
    strs = [str(r) for r in rows]
    if len(strs) == 1:
        return strs[0]
    if len(strs) == 2:
        return f"{strs[0]} and {strs[1]}"
    return ", ".join(strs[:-1]) + f", and {strs[-1]}"


def _format_quality_report(result, fk_target_labels=None):
    """
    Formats a QualityResult into the human-readable report. Kept
    entirely separate from quality.py's check_data() — the core
    checker returns structured data and never prints, so a future
    --format json (not yet built) doesn't require touching the
    checking logic at all.

    fk_target_labels maps a foreign_key source field name to a
    display string like "dq_customers.customer_id", purely for a
    friendlier report line — check_data()/QualityIssue itself has no
    concept of "target_table.target_column" display formatting.
    """
    fk_target_labels = fk_target_labels or {}

    print(f"✓ Loaded data: {result.rows_checked} rows")
    print()

    if result.is_valid:
        print("✓ No data-quality issues found")
        return

    print(f"✗ {len(result.issues)} issue(s) found")

    required = [i for i in result.issues if i.rule == "required"]
    uniqueness = [i for i in result.issues if i.rule == "uniqueness"]
    accepted_values = [i for i in result.issues if i.rule == "accepted_values"]
    range_issues = [i for i in result.issues if i.rule == "range"]
    pattern_issues = [i for i in result.issues if i.rule == "pattern"]
    foreign_key_issues = [i for i in result.issues if i.rule == "foreign_key"]

    if required:
        print("\nRequired-field violations:")
        for issue in required:
            for row in issue.rows:
                print(f"  - {issue.field} is blank at data row {row}")

    if uniqueness:
        print("\nUniqueness violations:")
        for issue in uniqueness:
            print(f"  - {issue.field} '{issue.value}' appears in data rows {_join_rows(issue.rows)}")

    if accepted_values:
        print("\naccepted_values violations:")
        for issue in accepted_values:
            row_label = "data row" if len(issue.rows) == 1 else "data rows"
            print(
                f"  - {issue.field} '{issue.value}' at {row_label} "
                f"{_join_rows(issue.rows)} not in the accepted set"
            )

    if range_issues:
        print("\nRange violations:")
        for issue in range_issues:
            row_label = "data row" if len(issue.rows) == 1 else "data rows"
            print(
                f"  - {issue.field} '{issue.value}' at {row_label} "
                f"{_join_rows(issue.rows)} out of range"
            )

    if pattern_issues:
        print("\nPattern violations:")
        for issue in pattern_issues:
            row_label = "data row" if len(issue.rows) == 1 else "data rows"
            print(
                f"  - {issue.field} '{issue.value}' at {row_label} "
                f"{_join_rows(issue.rows)} does not match the expected pattern"
            )

    if foreign_key_issues:
        print("\nForeign-key violations:")
        for issue in foreign_key_issues:
            target = fk_target_labels.get(issue.field, "the referenced dataset")
            row_label = "data row" if len(issue.rows) == 1 else "data rows"
            print(
                f"  - {issue.field} '{issue.value}' at {row_label} "
                f"{_join_rows(issue.rows)} not found in {target}"
            )


def _parse_ref_args(ref_args):
    """
    Parses --ref alias=schema.yml:data.csv into
    {alias: (schema_path, data_path)}. Raises a clear error on a
    malformed --ref rather than an obscure downstream failure.
    """
    refs = {}
    for raw in ref_args or []:
        if "=" not in raw or ":" not in raw.split("=", 1)[1]:
            raise ValueError(
                f"Invalid --ref '{raw}' — expected format: "
                f"alias=schema.yml:data.csv"
            )
        alias, rest = raw.split("=", 1)
        schema_path, data_path = rest.split(":", 1)
        refs[alias] = (schema_path, data_path)
    return refs


def validate_data(args):
    try:
        table = load_spec(args.spec)
        validate_table(table)

    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ValueError as e:
        print("\nSchema validation failed:\n")
        print(e)
        return False

    print(f"✓ Loaded schema: {table.name}")

    try:
        ref_paths = _parse_ref_args(getattr(args, "ref", None))

        loaded_refs = {}
        for alias, (schema_path, data_path) in ref_paths.items():
            ref_schema = load_spec(schema_path)
            validate_table(ref_schema)
            ref_rows = load_data_rows(data_path)
            loaded_refs[alias] = (ref_schema, ref_rows)

        referenced_values = resolve_references(table, loaded_refs)

    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ValueError as e:
        print("\nForeign-key configuration error:\n")
        print(e)
        return False

    fk_target_labels = {}
    for constraint in table.constraints:
        if constraint.type == "foreign_key":
            source_column = constraint.columns[0]
            fk_target_labels[source_column] = (
                f"{constraint.target_table}.{constraint.target_column}"
            )

    try:
        rows = load_data_rows(args.data)
    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False

    result = check_data(table, rows, referenced_values=referenced_values)

    _format_quality_report(result, fk_target_labels=fk_target_labels)
    return True


def _parse_schema_data_arg(raw):
    """
    Parses schema.yml:data.csv into (schema_path, data_path) — the
    same colon-pair convention --ref already uses, minus the
    alias= prefix (reconcile's old/new positional args are
    unambiguous by position, unlike --ref's repeatable list).
    """
    if ":" not in raw:
        raise ValueError(
            f"Invalid argument '{raw}' — expected format: schema.yml:data.csv"
        )
    schema_path, data_path = raw.split(":", 1)
    return schema_path, data_path


def _format_reconciliation_report(result):
    """
    Formats a ReconciliationResult into the human-readable report.
    Kept separate from reconciliation.py's reconcile_data() the same
    way _format_quality_report is kept separate from check_data() —
    the checker returns structured data and never prints.
    """
    print()
    print("Row counts:")
    print(f"  old: {result.old_count}")
    print(f"  new: {result.new_count}")
    print(f"  matched: {result.matched_count}")

    if result.is_reconciled:
        print("\n✓ No reconciliation issues found")
        return

    print(f"\n✗ {len(result.issues)} issue(s) found")

    row_coverage = [i for i in result.issues if i.category == "row_coverage"]
    aggregate = [i for i in result.issues if i.category == "aggregate"]

    if row_coverage:
        print("\nRow matching:")
        for issue in row_coverage:
            label = "row" if len(issue.keys) == 1 else "rows"
            print(f"  - {issue.rule}: {len(issue.keys)} {label}")
            for key in issue.keys:
                print(f"      key={key}")

    if aggregate:
        print("\nAggregate comparison (matched rows):")
        for issue in aggregate:
            print(
                f"  - {issue.field}: old_sum={issue.old_value}  "
                f"new_sum={issue.new_value}  diff={issue.diff}"
            )


def reconcile(args):
    """
    New-direction, v1 — given two datasets meant to represent the
    same logical output (e.g. a legacy system's output and its
    Snowflake replacement), reports row-population coverage
    (missing_in_new / missing_in_old, by key) and aggregate
    equivalence on declared measures, restricted to the matched
    population. Does not claim per-field semantic equivalence — see
    reconciliation.py's reconcile_data() docstring for the exact
    scope boundary and why aggregates are computed on matched rows
    only, not the full old/new populations.
    """
    try:
        old_schema_path, old_data_path = _parse_schema_data_arg(args.old)
        new_schema_path, new_data_path = _parse_schema_data_arg(args.new)
    except ValueError as e:
        print(f"\n{e}")
        return False

    try:
        old_table = load_spec(old_schema_path)
        validate_table(old_table)
        new_table = load_spec(new_schema_path)
        validate_table(new_table)
    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ValueError as e:
        print("\nSchema validation failed:\n")
        print(e)
        return False

    print(f"✓ Loaded schemas: {old_table.name} (old), {new_table.name} (new)")

    try:
        mapping = load_reconciliation_mapping(args.mapping)
        validate_mapping(mapping, old_table, new_table)
    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ValueError as e:
        print("\nMapping configuration error:\n")
        print(e)
        return False

    try:
        old_rows = load_data_rows(old_data_path)
        new_rows = load_data_rows(new_data_path)
    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False

    print(f"✓ Loaded data: {len(old_rows)} old row(s), {len(new_rows)} new row(s)")

    result = reconcile_data(old_table, old_rows, new_table, new_rows, mapping)

    _format_reconciliation_report(result)
    return True


def deps(args):
    """
    Phase 7 remainder — dataset dependency tracking. Loads and
    validates multiple dataset YAML files together, then reports a
    safe processing order (or a clear error: schema validation
    failure, unresolved dependency reference, duplicate dataset
    name, or circular dependency).

    Declaration/ordering only — see dependencies.py's module
    docstring for the explicit scope boundary. This command does not
    resolve or generate anything about HOW one dataset obtains
    another's data.
    """
    tables = []

    for path in args.paths:
        try:
            table = load_spec(path)
            validate_table(table)
        except FileNotFoundError as e:
            print(f"\nFile not found: {e.filename}")
            return False
        except ValueError as e:
            print(f"\nValidation failed for {path}:\n")
            print(e)
            return False
        tables.append(table)

    print(f"✓ Loaded {len(tables)} dataset(s)")

    try:
        order = execution_order(tables)
    except ValueError as e:
        print("\nDependency resolution failed:\n")
        print(e)
        return False

    print("\n--- EXECUTION ORDER ---\n")
    for i, name in enumerate(order, start=1):
        print(f"{i}. {name}")
    return True


def impact(args):
    """
    Phase 9, v1 -- impact analysis. Loads and validates multiple
    dataset YAML files together, then reports every dataset that
    depends on args.dataset_name, directly or transitively, in the
    order they'd need to be regenerated (or a clear error: schema
    validation failure, unresolved dependency reference, duplicate
    dataset name, circular dependency, or an unknown dataset name).

    See dependencies.py's impacted_by() for the full contract.
    """
    tables = []

    for path in args.paths:
        try:
            table = load_spec(path)
            validate_table(table)
        except FileNotFoundError as e:
            print(f"\nFile not found: {e.filename}")
            return False
        except ValueError as e:
            print(f"\nValidation failed for {path}:\n")
            print(e)
            return False
        tables.append(table)

    print(f"✓ Loaded {len(tables)} dataset(s)")

    try:
        impacted = impacted_by(args.dataset_name, tables)
    except ValueError as e:
        print("\nDependency resolution failed:\n")
        print(e)
        return False

    print(f"\n--- IMPACTED BY '{args.dataset_name}' ---\n")
    if not impacted:
        print(f"(no datasets depend on '{args.dataset_name}')")
    else:
        for i, name in enumerate(impacted, start=1):
            print(f"{i}. {name}")
    return True


def execute(args):
    """
    Phase 8 — Execution and Platform Integrations.
    Executes a dataset's generated DDL against a real database engine
    (DuckDB or PostgreSQL — see executors/registry.py), optionally
    loading real data and running a verification query.

    Phase 8C-v1: the DROP (if --drop-if-exists), CREATE, and row-load
    (or model INSERT — see below) steps run inside a single
    executor.transaction() scope — atomic as a whole. A failure
    partway through (e.g. a duplicate-key row in --data, or a real
    constraint violation during --materialize) rolls back everything
    from this invocation, including the DROP and CREATE — leaving the
    database exactly as it was before the invocation, not silently
    half-populated. The verification query runs after the transaction
    commits, so it proves durable persistence, not just in-transaction
    visibility. Re-running against an existing table still fails
    loudly unless --drop-if-exists is passed — no silent overwrite/
    append; --materialize does not change this in any way, it only
    changes how the table gets its rows once CREATE succeeds.

    Phase 8D v4: --materialize populates the table by running its
    transformation model's SELECT (ModelGenerator.generate_insert(),
    Phase 8D v3) instead of loading raw --data — mutually exclusive
    with --data, since they're two different ways of populating the
    same rows. Requires the dataset to declare computed fields and/or
    sources/joins (checked before connecting to the database — a
    dataset with nothing to materialize, or one whose model reads
    from a relation sharing its own name, fails fast with a clear
    error, never a wasted connection). Assumes any upstream tables the
    model reads from already exist and are already populated in the
    target database — structifact execute does not create, populate,
    or orchestrate across datasets; that remains explicitly out of
    scope (see docs/FUTURE_WORK.md).

    Connection pooling and retry logic (Executor.transaction()'s
    retry_transaction(), Phase 8C-v2) remain deliberately unexposed
    here — no real caller of this command has a concurrent-writer or
    connection-reuse need yet. See docs/FUTURE_WORK.md.
    """
    try:
        table = load_spec(args.spec)
        validate_table(table)
    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ValueError as e:
        print("\nValidation failed:\n")
        print(e)
        return False

    print(f"✓ Loaded schema: {table.name}")

    if getattr(args, "materialize", False) and args.data:
        print(
            "\n--materialize and --data cannot be used together — "
            "--materialize populates the table by running its model's "
            "SELECT; --data loads raw CSV rows directly."
        )
        return False

    insert_artifact = None
    if getattr(args, "materialize", False):
        try:
            insert_artifact = ModelGenerator().generate_insert(table)
        except ValueError as e:
            print(f"\nCannot materialize '{table.name}':\n")
            print(e)
            return False

        if insert_artifact is None:
            print(
                f"\n'{table.name}' has no computed fields or sources/joins "
                "declared — nothing to materialize."
            )
            return False

    executor_cls = EXECUTORS.get(args.engine)
    if executor_cls is None:
        print(f"\nUnknown engine '{args.engine}'")
        print(f"Available: {', '.join(sorted(EXECUTORS.keys()))}")
        return False

    executor = executor_cls()

    connection_args = {}
    if args.connection:
        connection_args["connection"] = args.connection

    try:
        executor.connect(**connection_args)
    except Exception as e:
        print("\nConnection failed:\n")
        print(e)
        return False

    connection_label = f" ({args.connection})" if args.connection else " (in-memory)"
    print(f"✓ Connected: {executor.name}{connection_label}")

    try:
        with executor.transaction():
            if getattr(args, "drop_if_exists", False):
                executor.execute_ddl(f"DROP TABLE IF EXISTS {table.name}")
                print(f"✓ Dropped table '{table.name}' if it existed")

            ddl_artifact = SQLGenerator().generate(table)
            executor.execute_ddl(ddl_artifact.content)
            print(f"✓ Executed DDL: CREATE TABLE {table.name} (...)")

            if getattr(args, "materialize", False):
                executor.execute_ddl(insert_artifact.content)
                print(f"✓ Executed model INSERT: INSERT INTO {table.name} (...)")
            elif args.data:
                rows = load_data_rows(args.data)
                columns = [f.name for f in table.fields]
                executor.load_rows(table.name, columns, rows)
                print(f"✓ Loaded {len(rows)} rows")

        # Only reached if the transaction above committed successfully —
        # this query runs against durably persisted data, not merely
        # in-transaction visibility.
        if args.data or getattr(args, "materialize", False):
            result = executor.query(f"SELECT * FROM {table.name}")
            print(f"✓ Verification query: {len(result)} rows in {table.name}")

        if getattr(args, "materialize", False):
            outcome = "created and materialized"
        elif args.data:
            outcome = "created and populated"
        else:
            outcome = "created"
        print(f"\nTable '{table.name}' {outcome} successfully.")

    except Exception as e:
        print("\nExecution failed:\n")
        print(e)
        return False
    finally:
        executor.close()

    return True


def discover(args, ai_client=None):
    if args.spec.lower().endswith((".md", ".txt", ".xlsx")):
        return discover_requirements(args, ai_client=ai_client)

    if not args.spec.lower().endswith(".csv"):
        print(
            "\nstructifact discover currently only supports raw CSV "
            "input, or a requirements document (.md/.txt/.xlsx) with --ai."
        )
        return False

    try:
        discovered = discover_csv(args.spec, sample_size=args.sample_size)
    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ValueError as e:
        print(f"\n{e}")
        return False

    sampled = min(discovered.row_count, args.sample_size)

    print(f"✓ Read {discovered.row_count} row(s)")
    print(f"✓ Sampled {sampled} row(s)")
    print(f"✓ Inferred {len(discovered.fields)} column(s)")

    ai_suggestions = None

    if getattr(args, "ai", False):
        if ai_client is None:
            from .llm import AnthropicLLMClient

            try:
                ai_client = AnthropicLLMClient()
            except RuntimeError as e:
                print(f"\n{e}")
                return False

        prompt = build_ai_prompt(discovered)
        estimate = ai_client.estimate_cost(prompt)

        print(f"\nAI-assisted field descriptions requested.")
        print(f"Estimate: {estimate.note}")

        proceed = getattr(args, "yes", False)

        if not proceed:
            answer = input("Proceed with this request? [y/N] ").strip().lower()
            proceed = answer == "y"

        if proceed:
            raw = ai_client.suggest_field_descriptions(prompt)
            ai_suggestions = parse_ai_suggestions(raw)
        else:
            print("Skipped — writing deterministic draft only (no AI request made).")

    yaml_content = render_draft_yaml(discovered, ai_suggestions=ai_suggestions)

    output_path = args.output or f"{discovered.name}.discovered.yml"
    write_file(output_path, yaml_content)

    print(f"✓ Wrote draft metadata to {output_path}")
    print("\nThis is a draft, not verified metadata. Review it, fix")
    print("anything wrong, then run:")
    print(f"\n  structifact validate {output_path}\n")
    return True


def discover_requirements(args, ai_client=None):
    """
    AI-assisted schema extraction from a raw requirements document
    (.md/.txt/.xlsx). Unlike raw-data discovery, there is no
    deterministic half here — a requirements document has no data
    rows to sample — so this path always requires --ai and does
    nothing without it.
    """
    if not getattr(args, "ai", False):
        print(
            "\nA requirements document has no data rows to sample, so "
            "structifact can only draft a schema from one with --ai "
            "(this reads the document with an LLM; nothing here is "
            "generated deterministically)."
        )
        return False

    try:
        if args.spec.lower().endswith(".xlsx"):
            text = extract_text_from_xlsx(args.spec)
        else:
            with open(args.spec, "r") as f:
                text = f.read()
    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ImportError:
        print(
            "\nReading a .xlsx requirements document requires the "
            '\'excel\' extra: pip install -e ".[excel]"'
        )
        return False

    if ai_client is None:
        from .llm import AnthropicLLMClient

        try:
            ai_client = AnthropicLLMClient()
        except RuntimeError as e:
            print(f"\n{e}")
            return False

    prompt = build_requirements_prompt(text)
    estimate = ai_client.estimate_cost(prompt)

    print(f"\nAI-assisted requirements-document extraction requested.")
    print(f"Estimate: {estimate.note}")

    proceed = getattr(args, "yes", False)

    if not proceed:
        answer = input("Proceed with this request? [y/N] ").strip().lower()
        proceed = answer == "y"

    if not proceed:
        print("Skipped — no AI request made, nothing written.")
        return

    raw = ai_client.complete(prompt)

    try:
        parsed = parse_requirements_draft(raw)
    except ValueError as e:
        print(f"\nCouldn't parse the AI response:\n\n{e}")
        return False

    yaml_content = render_requirements_draft_yaml(parsed, source_path=args.spec)

    dataset_name = parsed.get("dataset", "requirements")
    output_path = args.output or f"{dataset_name}.discovered.yml"
    write_file(output_path, yaml_content)

    print(f"✓ Wrote draft metadata to {output_path}")
    print("\nThis is a first-pass AI extraction, not verified metadata.")
    print("Review it — especially any 'computed' fields and everything")
    print("under unresolved_notes — then run:")
    print(f"\n  structifact validate {output_path}\n")
    return True


def generate(args):
    try:
        table = load_spec(args.spec)
        validate_table(table)

    except FileNotFoundError as e:
        print(f"\nFile not found: {e.filename}")
        return False
    except ValueError as e:
        print("\nValidation failed:\n")
        print(e)
        return False

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
            return False

        selected = [by_name[n] for n in requested]
    else:
        selected = GENERATORS

    for gen in selected:
        artifact = gen.generate(table)

        # generate() may return None to mean "nothing to generate
        # for this dataset" (see generators/base.py) — e.g.
        # ModelGenerator for a dataset with no computed fields and no
        # sources/joins. A valid result, not an error -- say so
        # explicitly (matching how `execute --materialize` explains
        # the identical case) rather than silently printing nothing,
        # which previously left a "GENERATED ARTIFACTS" header with
        # no explanation for why nothing followed it.
        if artifact is None:
            print(f"- {gen.name}: nothing to generate for this dataset")
            continue

        path = f"{args.output}/{artifact.filename}"

        write_file(path, artifact.content)

        print(f"- {path}")

    return True


def main():
    parser = argparse.ArgumentParser(
        prog="structifact",
        description="Define once. Generate everywhere."
    )

    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser("validate")

    validate_parser.add_argument("spec")

    validate_parser.set_defaults(func=validate)

    validate_data_parser = subparsers.add_parser(
        "validate-data",
        help=(
            "Check real data rows against a dataset's already-declared "
            "metadata rules: required fields, uniqueness, accepted "
            "values, numeric ranges, regex patterns, and foreign-key "
            "relationships against a second dataset's real data "
            "(--ref). No type coercion — comparisons are on raw CSV "
            "string values."
        ),
    )

    validate_data_parser.add_argument("spec")
    validate_data_parser.add_argument("data")

    validate_data_parser.add_argument(
        "--ref", action="append", default=None,
        help=(
            "Reference another dataset for foreign-key checking: "
            "alias=schema.yml:data.csv, where alias matches a "
            "foreign_key constraint's target_table. Repeatable for "
            "multiple references. Required if the schema declares "
            "any foreign_key constraints — running without a needed "
            "--ref is a configuration error, not a silently-skipped "
            "check."
        ),
    )

    validate_data_parser.set_defaults(func=validate_data)

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

    reconcile_parser = subparsers.add_parser(
        "reconcile",
        help=(
            "Compare two datasets meant to represent the same logical "
            "output (e.g. a legacy system's data and its replacement's) "
            "and report row-population coverage (rows only in one side) "
            "and aggregate equivalence on declared measures, restricted "
            "to rows present on both sides. Does not compare individual "
            "field values row by row -- see docs for the exact v1 scope."
        ),
    )

    reconcile_parser.add_argument(
        "old", help="old_schema.yml:old_data.csv"
    )
    reconcile_parser.add_argument(
        "new", help="new_schema.yml:new_data.csv"
    )
    reconcile_parser.add_argument(
        "--mapping", required=True,
        help=(
            "Path to a reconciliation mapping YAML file declaring the "
            "old<->new key field and any other old<->new field pairs "
            "to compare (aggregate comparison uses whichever mapped "
            "fields the new schema declares role: measure)."
        ),
    )

    reconcile_parser.set_defaults(func=reconcile)

    deps_parser = subparsers.add_parser(
        "deps",
        help=(
            "Resolve dataset dependencies across multiple metadata "
            "files and report a safe execution order (or a circular-"
            "dependency error). Declaration/ordering only — does not "
            "resolve or generate anything about how one dataset "
            "obtains another's data."
        ),
    )

    deps_parser.add_argument(
        "paths", nargs="+",
        help="One or more dataset YAML files to resolve together.",
    )

    deps_parser.set_defaults(func=deps)

    impact_parser = subparsers.add_parser(
        "impact",
        help=(
            "Report every dataset that depends on a given dataset, "
            "directly or transitively, across multiple metadata "
            "files (or a circular-dependency/unresolved-reference "
            "error). Declaration/ordering only -- does not resolve "
            "or generate anything about how one dataset obtains "
            "another's data."
        ),
    )

    impact_parser.add_argument(
        "dataset_name",
        help="Name of the dataset to analyze impact for (as declared in metadata, not a file path).",
    )
    impact_parser.add_argument(
        "paths", nargs="+",
        help="One or more dataset YAML files to resolve together.",
    )

    impact_parser.set_defaults(func=impact)

    execute_parser = subparsers.add_parser(
        "execute",
        help=(
            "Execute a dataset's generated DDL against a real database "
            "engine, optionally loading real --data or --materialize-ing "
            "its transformation model, then verifying it. Real "
            "implementations: DuckDB (local file or in-memory, no "
            "credentials needed) and PostgreSQL (via a --connection DSN). "
            "The Executor interface is designed for further engines "
            "(Snowflake, ...) to slot in later without a redesign — see "
            "FUTURE_WORK.md's 'Before a 1.0 Release' section for what's "
            "not built yet."
        ),
    )

    execute_parser.add_argument("spec")

    execute_parser.add_argument(
        "--engine", required=True,
        help="Which Executor to use ('duckdb' or 'postgres'). Required — no default engine.",
    )

    execute_parser.add_argument(
        "--connection", default=None,
        help=(
            "Opaque connection string, interpreted by the chosen engine. "
            "For duckdb: a file path, or omit for an in-memory database. "
            "For postgres: a DSN, e.g. postgresql://user:pass@host:port/dbname "
            "(required — postgres has no in-memory default)."
        ),
    )

    execute_parser.add_argument(
        "--data", default=None,
        help="Optional CSV of real data rows to load and verify after DDL execution.",
    )

    execute_parser.add_argument(
        "--materialize", action="store_true",
        help=(
            "Populate the table by running its transformation model's "
            "SELECT (ModelGenerator) instead of loading raw --data. "
            "Requires the dataset to declare computed fields and/or "
            "sources/joins. Assumes any upstream tables the model "
            "reads from already exist and are populated in the target "
            "database -- structifact execute does not create or "
            "populate them. Mutually exclusive with --data."
        ),
    )

    execute_parser.add_argument(
        "--drop-if-exists", action="store_true", dest="drop_if_exists",
        help=(
            "Drop the target table first, if it already exists, before "
            "running CREATE TABLE. Off by default — re-running execute "
            "against an existing table without this flag fails loudly "
            "rather than silently overwriting or appending."
        ),
    )

    execute_parser.set_defaults(func=execute)

    discover_parser = subparsers.add_parser("discover")

    discover_parser.add_argument(
        "spec",
        help=(
            "Path to a raw CSV data file, or a requirements document "
            "(.md/.txt) — requirements documents require --ai."
        ),
    )

    discover_parser.add_argument("-o", "--output", default=None)

    discover_parser.add_argument(
        "-n", "--sample-size", type=int, default=100
    )

    discover_parser.add_argument(
        "--ai", action="store_true",
        help=(
            "Ask an LLM to help with discovery: suggests field "
            "descriptions for CSV input, or extracts a draft schema "
            "from a requirements document (.md/.txt). Requires "
            "ANTHROPIC_API_KEY. Off by default — never runs, never "
            "costs anything, unless you pass this explicitly. Shows "
            "a cost estimate and asks for confirmation before making "
            "any request, unless -y is also passed. Required (not "
            "optional) for requirements-document input, since there "
            "is no deterministic way to parse freeform text."
        ),
    )

    discover_parser.add_argument(
        "-y", "--yes", action="store_true",
        help="Skip the confirmation prompt when using --ai.",
    )

    discover_parser.set_defaults(func=discover)

    args = parser.parse_args()

    if hasattr(args, "func"):
        success = args.func(args)
        # Handlers return False on a genuine failure (validation,
        # missing file, connection/execution error, etc.) and True or
        # None otherwise -- None covers handlers/branches that were
        # never audited for an explicit return, so an unaudited path
        # still exits 0 rather than accidentally starting to fail CI.
        if success is False:
            sys.exit(1)
    else:
        parser.print_help()
