from dataclasses import dataclass
from ..ir import DatasetSpec


@dataclass
class Artifact:
    filename: str
    content: str


class Generator:
    name: str

    def generate(self, dataset: DatasetSpec) -> Artifact:
        raise NotImplementedError