import re


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

# YYYY-MM-DD, optionally followed by a time component (space or "T")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?")


def infer_type_from_values(values: list) -> str:
    """
    Infer a normalized Structifact type from a list of raw sample
    values (as strings), the way `structifact discover` does when
    it hasn't been told what type a column is.

    This is deliberately conservative: if the sample is empty, or
    values disagree with each other in a way that doesn't fit one
    type cleanly, this returns "unknown" rather than guessing.
    """
    non_empty = [v.strip() for v in values if v is not None and str(v).strip() != ""]

    if not non_empty:
        return "unknown"

    if all(v.lower() in _BOOLEAN_VALUES for v in non_empty):
        return "boolean"

    if all(_TIMESTAMP_RE.match(v) for v in non_empty):
        return "timestamp"

    if all(_DATE_RE.match(v) for v in non_empty):
        return "date"

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
