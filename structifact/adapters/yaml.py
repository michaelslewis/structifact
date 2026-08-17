from decimal import Decimal

import yaml

from ..ir import (
    DatasetSpec, FieldSpec, ConstraintSpec, SourceRef, JoinSpec, DedupRule,
    AggregateRule,
)
from ..types import parse_type


def _parse_bound(raw):
    """
    Converts a YAML-parsed numeric literal (already a Python int or
    float by the time PyYAML hands it to us) into a Decimal via
    str() rather than a direct Decimal(raw) call — see FieldSpec's
    min_value/max_value docstring in ir.py for why: Decimal(a_float)
    preserves that float's exact binary representation rather than
    the clean decimal value the person actually wrote in the YAML
    file, and str() recovers it since Python's float-to-str is
    round-trip-safe for ordinary decimal literals.
    """
    if raw is None:
        return None
    return Decimal(str(raw))


def load_yaml(path: str) -> DatasetSpec:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if "dataset" in data:
        dataset = data["dataset"]

        name = dataset["name"]
        description = dataset.get("description")
    else:
        name = data["table"]
        description = None

    fields = []

    for field in data["fields"]:
        parsed = parse_type(field["type"])

        raw_accepted_values = field.get("accepted_values")
        accepted_values = (
            [str(v) for v in raw_accepted_values]
            if raw_accepted_values is not None
            else None
        )

        raw_depends_on = field.get("depends_on")
        depends_on = (
            [str(v) for v in raw_depends_on]
            if raw_depends_on is not None
            else None
        )

        fields.append(
            FieldSpec(
                name=field["name"],
                type=parsed["type"],
                raw_type=field["type"],
                description=field.get("description"),
                comment=field.get("comment"),
                role=field.get("role"),
                accepted_values=accepted_values,

                length=parsed.get("length"),
                precision=parsed.get("precision"),
                scale=parsed.get("scale"),

                nullable=field.get("nullable", True),

                computed=field.get("computed", False),
                expression=field.get("expression"),
                depends_on=depends_on,

                min_value=_parse_bound(field.get("min_value")),
                max_value=_parse_bound(field.get("max_value")),
                pattern=field.get("pattern"),

                source=field.get("source"),
                source_column=field.get("source_column"),
            )
        )

    constraints = [
        ConstraintSpec(
            type=constraint["type"],
            columns=constraint["columns"],
            target_table=constraint.get("target_table"),
            target_column=constraint.get("target_column"),
            expression=constraint.get("expression"),
        )
        for constraint in data.get("constraints", [])
    ]

    # Phase 7 remainder — dataset dependency tracking. Top-level key,
    # sibling to `dataset:`/`fields:`/`constraints:` — same placement
    # precedent as `constraints`, which is also parsed from the top
    # level rather than nested inside `dataset:`. NOT the same thing
    # as a field's own `depends_on` above (that's parsed per-field,
    # inside `fields:`).
    raw_dataset_depends_on = data.get("depends_on")
    dataset_depends_on = (
        [str(v) for v in raw_dataset_depends_on]
        if raw_dataset_depends_on is not None
        else []
    )

    # Phase 7 — sources/joins milestone, and source_table/source_filter
    # (also Phase 7, the latter added from real-world use). Top-level
    # keys, siblings to `constraints`/`depends_on` above — same
    # placement precedent, and matching ARCHITECTURE.md's own
    # documented DatasetSpec shape. `source_table` was previously never
    # actually parsed here despite being fully supported by
    # validation.py/ModelGenerator ever since Phase 7 — every existing
    # sources/joins test only ever constructed DatasetSpec directly, so
    # the gap was invisible until a real YAML file exercised it (see
    # DECISION_HISTORY.md) -- `source_filter` is wired in from the
    # start this time, learning from that.
    source_table = data.get("source_table")
    source_filter = data.get("source_filter")

    # dbt-target metadata (also real-world-use-driven, confirmed by a
    # second independent real example before being added — see
    # DECISION_HISTORY.md). Flat top-level keys, same placement
    # precedent as source_table/source_filter above, one-to-one with
    # the DatasetSpec field names. Wired in from the start, same as
    # source_filter was.
    dbt_schema = data.get("dbt_schema")
    dbt_tags = [str(v) for v in data.get("dbt_tags", [])]
    dbt_datasource_name = data.get("dbt_datasource_name")
    dbt_datasource_project = data.get("dbt_datasource_project")
    dbt_datasource_extract = data.get("dbt_datasource_extract")
    dbt_data_catalog = data.get("dbt_data_catalog")

    sources = [
        SourceRef(
            name=source["name"],
            table=source["table"],
            filter=source.get("filter"),
            dedup=(
                DedupRule(
                    partition_by=[str(v) for v in source["dedup"]["partition_by"]],
                    order_by=[str(v) for v in source["dedup"]["order_by"]],
                )
                if source.get("dedup") is not None
                else None
            ),
            aggregate=(
                AggregateRule(
                    group_by=[str(v) for v in source["aggregate"]["group_by"]],
                    aggregates={
                        str(k): str(v)
                        for k, v in source["aggregate"]["aggregates"].items()
                    },
                )
                if source.get("aggregate") is not None
                else None
            ),
        )
        for source in data.get("sources", [])
    ]

    joins = [
        JoinSpec(
            source=join["source"],
            on=join["on"],
            type=join.get("type", "left"),
        )
        for join in data.get("joins", [])
    ]

    return DatasetSpec(
        name=name,
        description=description,
        fields=fields,
        constraints=constraints,
        depends_on=dataset_depends_on,
        source_table=source_table,
        source_filter=source_filter,
        dbt_schema=dbt_schema,
        dbt_tags=dbt_tags,
        dbt_datasource_name=dbt_datasource_name,
        dbt_datasource_project=dbt_datasource_project,
        dbt_datasource_extract=dbt_datasource_extract,
        dbt_data_catalog=dbt_data_catalog,
        sources=sources,
        joins=joins,
    )
