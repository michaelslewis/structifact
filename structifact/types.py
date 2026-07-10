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