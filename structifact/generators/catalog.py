import csv
import io

from .base import Generator, Artifact
from ..ir import DatasetSpec


def _length_display(f) -> str:
    if f.type == "decimal" and f.precision is not None and f.scale is not None:
        return f"{f.precision},{f.scale}"

    if f.length is not None:
        return str(f.length)

    return ""


class CatalogCSVGenerator(Generator):
    name = "catalog"

    def generate(self, table: DatasetSpec) -> Artifact:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")

        writer.writerow(["name", "description", "role", "type", "length"])

        for f in table.fields:
            writer.writerow([
                f.name,
                f.description or "",
                f.role or "",
                f.type,
                _length_display(f),
            ])

        return Artifact(
            filename=f"{table.name}_catalog.csv",
            content=buf.getvalue()
        )
