from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class FieldSpec:
    """
    Represents a single dataset field.

    FieldSpec contains intrinsic characteristics of a field.
    Relational or business rules should be represented separately
    through ConstraintSpec.
    """

    name: str
    type: str

    raw_type: Optional[str] = None

    description: Optional[str] = None
    label: Optional[str] = None

    role: Optional[str] = None  # dimension | measure
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None

    nullable: bool = True


@dataclass
class ConstraintSpec:
    """
    Represents a dataset-level constraint.

    Constraints describe rules or relationships that do not
    belong directly on an individual field.

    Examples:
    - primary_key
    - unique
    - foreign_key
    - check
    """

    type: str
    columns: List[str]


@dataclass
class DatasetSpec:
    """
    Canonical intermediate representation for a Structifact dataset.

    DatasetSpec replaces the previous TableSpec concept while
    remaining implementation-neutral. A dataset may eventually
    represent more than a relational database table.
    """

    name: str
    fields: List[FieldSpec]

    description: Optional[str] = None

    constraints: List[ConstraintSpec] = field(default_factory=list)


# Backwards compatibility during migration.
#
# TableSpec is intentionally an alias rather than a subclass because
# there is no specialized Table behavior. Existing code importing
# TableSpec should continue to work while DatasetSpec becomes the
# canonical IR name.
TableSpec = DatasetSpec