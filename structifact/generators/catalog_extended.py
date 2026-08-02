import csv
import io
import os
from datetime import datetime

from .base import Generator, Artifact
from .catalog import _length_display
from ..ir import DatasetSpec


class ExtendedCatalogCSVGenerator(Generator):
    """
    A catalog generator matching a specific downstream tool's expected
    column set: name, description, role, datatype, fieldlength, pii,
    comments, changed_by, changed_on.

    This is deliberately NOT run by default alongside SQL/dbt/the
    basic catalog generator (see generators/registry.py) — Structifact
    has no way to know whether any given user's downstream tooling
    needs this exact shape, so it's opt-in via `structifact generate
    -g catalog_extended`, not assumed.

    Structifact's IR has no concept of "pii" or a separate "comments"
    field distinct from description, so those columns are always
    blank rather than guessed. `changed_by` is blank unless supplied
    (constructor argument, or the STRUCTIFACT_CHANGED_BY environment
    variable) — never fabricated. `changed_on` is the one column that
    can be honestly populated automatically, since it's simply the
    real moment this file was generated.
    """

    name = "catalog_extended"

    def __init__(self, changed_by: str = None, now_fn=None):
        if changed_by is not None:
            self.changed_by = changed_by
        else:
            self.changed_by = os.environ.get("STRUCTIFACT_CHANGED_BY", "")

        self.now_fn = now_fn or datetime.now

    def generate(self, table: DatasetSpec) -> Artifact:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")

        writer.writerow([
            "name", "description", "role", "datatype", "fieldlength",
            "pii", "comments", "changed_by", "changed_on",
        ])

        changed_on = self.now_fn().strftime("%Y-%m-%d %H:%M:%S.%f")

        for f in table.fields:
            writer.writerow([
                f.name,
                f.description or "",
                f.role or "",
                f.type,
                _length_display(f),
                "",  # pii — not tracked by the IR, never guessed
                "",  # comments — not tracked by the IR, never guessed
                self.changed_by,
                changed_on,
            ])

        return Artifact(
            filename=f"{table.name}_catalog_extended.csv",
            content=buf.getvalue()
        )
