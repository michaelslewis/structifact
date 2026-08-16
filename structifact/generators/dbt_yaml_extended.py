import yaml

from .base import Generator, Artifact
from .dbt_yaml import _source_field
from ..ir import DatasetSpec


class DBTExtendedYAMLGenerator(Generator):
    """
    A dbt YAML generator matching a specific downstream dbt-based
    catalog/BI tool's expected dataset-level shape — `config.tags`,
    `schema`, a dataset `description`, and a `meta` block
    (`datasource_name`/`datasource_project`/`datasource_extract`/
    `data_catalog`) — none of which the plain `dbt` generator emits,
    and none of which exists anywhere in the core IR beyond the
    `dbt_*`-prefixed `DatasetSpec` fields this generator alone reads.

    This is deliberately NOT run by default (see
    generators/registry.py), the same reasoning as
    `ExtendedCatalogCSVGenerator`: Structifact has no way to know
    whether any given user's downstream tooling needs this exact
    shape, so it's opt-in via `structifact generate -g dbt_extended`,
    never assumed. Scoped from two independent real reference files
    (not one), which confirmed the same shape recurs — see
    DECISION_HISTORY.md.

    Column-level output (`role`, `source_field`) is identical to the
    plain `DBTYAMLGenerator` — this generator only adds dataset-level
    keys on top, duplicating the small per-column loop (sharing
    `_source_field`) rather than wrapping/calling the plain generator,
    the same relationship `catalog_extended.py` has to `catalog.py`.

    `dbt_tags` holds only the dataset's *extra* tags — the dataset's
    own name is always appended as the final tag automatically (both
    real examples ended their tag list with the dataset's own name).
    `dbt_datasource_name`, if unset, defaults to a title-cased,
    underscore-to-space version of the dataset name (both real
    examples matched this exactly). Every other `dbt_*` field is
    omitted entirely from the output when unset — never fabricated,
    even though both real examples happened to share the same values
    for `schema`/`datasource_project`/`datasource_extract`/
    `data_catalog`; that reflects one project's convention, not a
    universal default every Structifact user would want.
    """

    name = "dbt_extended"

    def generate(self, table: DatasetSpec) -> Artifact:
        columns = []
        for f in table.fields:
            meta = {}
            if f.role:
                meta["role"] = f.role
            meta["source_field"] = _source_field(f)

            columns.append({
                "name": f.name,
                "description": f.description or "",
                "meta": meta,
            })

        tags = list(table.dbt_tags) + [table.name]

        datasource_name = (
            table.dbt_datasource_name
            or table.name.replace("_", " ").title()
        )

        model_meta = {"datasource_name": datasource_name}
        if table.dbt_datasource_project:
            model_meta["datasource_project"] = table.dbt_datasource_project
        if table.dbt_datasource_extract is not None:
            model_meta["datasource_extract"] = table.dbt_datasource_extract
        if table.dbt_data_catalog is not None:
            model_meta["data_catalog"] = table.dbt_data_catalog

        model = {
            "name": table.name,
            "config": {"tags": tags},
        }
        if table.dbt_schema:
            model["schema"] = table.dbt_schema
        if table.description:
            model["description"] = table.description
        model["meta"] = model_meta
        model["columns"] = columns

        data = {
            "version": 2,
            "models": [model],
            "exposures": [],
        }

        return Artifact(
            filename=f"{table.name}_dbt_extended.yml",
            content=yaml.dump(data, sort_keys=False),
        )
