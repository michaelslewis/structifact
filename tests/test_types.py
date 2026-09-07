from structifact.types import parse_type, looks_like_padded_numeric


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


def test_looks_like_padded_numeric_true_for_leading_zero():
    assert looks_like_padded_numeric(["001", "002", "003"]) is True


def test_looks_like_padded_numeric_false_for_plain_integers():
    assert looks_like_padded_numeric(["1", "2", "3"]) is False


def test_looks_like_padded_numeric_false_for_free_text():
    assert looks_like_padded_numeric(["alice@example.com", "bob@example.com"]) is False


def test_looks_like_padded_numeric_ignores_null_tokens():
    assert looks_like_padded_numeric(["001", "", "NULL"]) is True