import re
from typing import List, Optional


TYPE_MAP = {
    "VARCHAR": "string",
    "VARCHAR2": "string",
    "CHAR": "string",
    "TEXT": "string",
    "STRING": "string",

    "INT": "integer",
    "INTEGER": "integer",
    "BIGINT": "integer",

    "DECIMAL": "decimal",
    "NUMBER": "decimal",
    "NUMERIC": "decimal",

    "FLOAT": "float",
    "DOUBLE": "float",

    "BOOLEAN": "boolean",
    "BOOL": "boolean",

    "DATE": "date",

    "TIMESTAMP": "timestamp",
    "TIMESTAMP_NTZ": "timestamp",
    "TIMESTAMP_LTZ": "timestamp",
    "TIMESTAMP_TZ": "timestamp",

    "DATETIME": "timestamp",
    "DATETIME2": "timestamp",
}


def normalize_type(raw_type: str) -> str:
    if not raw_type:
        return "unknown"

    base_type = re.split(
        r"\(",
        raw_type.upper()
    )[0].strip()

    return TYPE_MAP.get(
        base_type,
        "unknown"
    )

def parse_type(raw_type: str) -> dict:
    if not raw_type:
        return {
            "type": "unknown"
        }

    match = re.match(
        r"([A-Z0-9_]+)(?:\((.*?)\))?",
        raw_type.upper()
    )

    if not match:
        return {
            "type": "unknown"
        }

    base_type = match.group(1)
    parameters = match.group(2)

    result = {
        "type": TYPE_MAP.get(
            base_type,
            "unknown"
        )
    }

    if parameters:
        parts = [
            p.strip()
            for p in parameters.split(",")
        ]

        if len(parts) == 1:
            try:
                result["length"] = int(parts[0])
            except ValueError:
                pass

        elif len(parts) == 2:
            try:
                result["precision"] = int(parts[0])
                result["scale"] = int(parts[1])
            except ValueError:
                pass

    return result


_BOOLEAN_VALUES = {"true", "false"}
_NULL_TOKENS = {"null", "n/a", "na", "none", "nan", "-", "unknown"}

# YYYY-MM-DD, optionally followed by a time component (space or "T")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?")

# A value that looks numeric but starts with a zero and has more than
# one digit before any decimal point (e.g. "001", "02134") — treating
# these as integers silently destroys information, so they should be
# left as strings even though int() would happily parse them.
_LEADING_ZERO_RE = re.compile(r"^0\d+(\.\d+)?$")


def is_null_token(value) -> bool:
    """
    True if a raw sample value represents "no data" — either
    genuinely empty, or a common placeholder like NULL, N/A, -, etc.
    """
    if value is None:
        return True

    stripped = str(value).strip()

    return stripped == "" or stripped.lower() in _NULL_TOKENS


def infer_type_from_values(values: list) -> str:
    """
    Infer a normalized Structifact type from a list of raw sample
    values (as strings), the way `structifact discover` does when
    it hasn't been told what type a column is.

    This is deliberately conservative: if the sample is empty, or
    values disagree with each other (or contain a landmine like a
    leading-zero identifier) in a way that doesn't fit one type
    cleanly, this returns "unknown" or "string" rather than guessing.
    """
    non_empty = [v.strip() for v in values if not is_null_token(v)]

    if not non_empty:
        return "unknown"

    if all(v.lower() in _BOOLEAN_VALUES for v in non_empty):
        return "boolean"

    if all(_TIMESTAMP_RE.match(v) for v in non_empty):
        return "timestamp"

    if all(_DATE_RE.match(v) for v in non_empty):
        return "date"

    if any(_LEADING_ZERO_RE.match(v) for v in non_empty):
        # Looks numeric, but at least one value has a leading zero —
        # treat the whole column as a string rather than risk quietly
        # corrupting an identifier like a zip code or padded order ID.
        return "string"

    if all(_is_int(v) for v in non_empty):
        return "integer"

    if all(_is_float(v) for v in non_empty):
        return "decimal"

    return "string"


def _is_int(value: str) -> bool:
    try:
        int(value)
        return True
    except ValueError:
        return False


def _is_float(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


_TRUE_TOKENS = {"true", "1", "yes"}
_FALSE_TOKENS = {"false", "0", "no"}


def parse_bool(value, field_name: str, default: bool = True) -> bool:
    """
    Parse a boolean from a raw tabular cell (CSV/Excel don't have a
    native boolean type the way YAML does — everything arrives as
    text, or as None/NaN for a blank cell).

    A missing or blank cell returns `default`, matching the same
    default FieldSpec itself uses when a key is omitted entirely
    (e.g. nullable defaults to True). A cell with real, unrecognized
    text raises ValueError rather than silently guessing — an
    adapter silently misreading "flase" as some default would be a
    worse failure mode than a clear error surfaced through the same
    try/except ValueError path `structifact validate`/`generate`
    already use for bad metadata.
    """
    if value is None:
        return default

    text = str(value).strip()

    if text == "":
        return default

    lowered = text.lower()

    if lowered in _TRUE_TOKENS:
        return True

    if lowered in _FALSE_TOKENS:
        return False

    raise ValueError(
        f"Could not parse '{text}' as true/false for '{field_name}'"
    )


def parse_list(value) -> Optional[List[str]]:
    """
    Parse a semicolon-delimited list from a raw tabular cell (CSV/
    Excel have no native list type the way YAML does). Returns None
    for a missing/blank cell — "not specified", matching how the
    YAML adapter treats an absent accepted_values/depends_on key,
    rather than "specified as an empty list".
    """
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    return [part.strip() for part in text.split(";") if part.strip()]
