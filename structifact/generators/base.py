from dataclasses import dataclass
from ..ir import TableSpec


@dataclass
class Artifact:
    filename: str
    content: str


class Generator:
    name: str

    def generate(self, table: TableSpec) -> Artifact:
        raise NotImplementedError