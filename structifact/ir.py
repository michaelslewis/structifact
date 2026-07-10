from dataclasses import dataclass
from typing import Optional, List


@dataclass
class FieldSpec:
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
class TableSpec:
    name: str
    fields: List[FieldSpec]

    description: Optional[str] = None