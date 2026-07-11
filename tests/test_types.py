from structifact.types import parse_type


def test_varchar():
    result = parse_type("VARCHAR(255)")

    assert result["type"] == "string"
    assert result["length"] == 255


def test_number():
    result = parse_type("NUMBER(13,2)")

    assert result["type"] == "decimal"
    assert result["precision"] == 13
    assert result["scale"] == 2


def test_timestamp():
    result = parse_type("TIMESTAMP_NTZ")

    assert result["type"] == "timestamp"


def test_unknown():
    result = parse_type("banana")

    assert result["type"] == "unknown"