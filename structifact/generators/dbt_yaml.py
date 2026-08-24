from .base import Generator, Artifact
import yaml
from ..ir import DatasetSpec


def _source_field(f) -> str:
    """
    A field's own display name, with every underscore turned into a
    dot -- e.g. `struct_segmaster_ownerid_user` -> `struct.segmaster.ownerid.user`.

    Corrected after a second real reference file confirmed the first
    guess was wrong: this is NOT derived from the physical
    source/source_column (what the initial implementation assumed) --
    both real examples confirmed it identically, including the one
    field whose physical column itself contains an underscore
    (`ownerid_user`), which still gets split into `ownerid.user` here,
    proving the split operates on the field's own name, not on
    anything physical. See DECISION_HISTORY.md.
    """
    return f.name.replace("_", ".")


class DBTYAMLGenerator(Generator):
    """
    Generates dbt-compatible YAML metadata: name/description per
    column, plus (found via real-world use, confirmed by a second
    independent real example) `role` and `source_field`, and (found
    via real-world use, confirmed by a second, differently-shaped
    real example) `comment` — a second, independently-authored text
    label some downstream tooling expects alongside `description`.
    Omitted when unset, same as `role`.

    Still does NOT emit dataset-level dbt concepts (`config`/tags,
    `schema`, a dataset `description`, `meta` fields like
    `datasource_name`) — see `DBTExtendedYAMLGenerator` (`-g
    dbt_extended`) for those, kept as a separate opt-in generator
    rather than folded in here, the same pattern `catalog_extended`
    already established: Structifact has no way to know whether any
    given user's downstream tooling needs that shape, so it's never
    assumed for everyone by default.
    """

    name = "dbt"

    def generate(self, table: DatasetSpec) -> Artifact:
        columns = []
        for f in table.fields:
            meta = {}
            if f.role:
                meta["role"] = f.role
            meta["source_field"] = _source_field(f)
            if f.comment:
                meta["comment"] = f.comment

            columns.append({
                "name": f.name,
                "description": f.description or "",
                "meta": meta,
            })

        data = {
            "version": 2,
            "models": [
                {
                    "name": table.name,
                    "columns": columns,
                }
            ],
        }

        return Artifact(
            filename=f"{table.name}.yml",
            content=yaml.dump(data, sort_keys=False)
        )
