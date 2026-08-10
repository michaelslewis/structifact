from dataclasses import dataclass
from typing import Optional
from ..ir import DatasetSpec


@dataclass
class Artifact:
    filename: str
    content: str


class Generator:
    """
    Base class for all Structifact generators.

    generate() normally returns an Artifact to be written to disk.
    It may also return None to mean "nothing to generate for this
    dataset" — e.g. ModelGenerator (structifact/generators/model.py)
    returns None for a dataset with no computed fields, since there
    is nothing to transform and emitting an empty/no-op SELECT would
    just be clutter. Callers (see cli.py's generate()) must check for
    None and skip writing rather than assuming a return value is
    always a real Artifact.
    """

    name: str

    def generate(self, dataset: DatasetSpec) -> Optional[Artifact]:
        raise NotImplementedError
