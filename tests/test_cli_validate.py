import argparse

from structifact.cli import validate


def _args(spec):
    return argparse.Namespace(spec=spec)


def test_validate_valid_spec_prints_success(capsys):
    validate(_args("tests/fixtures/customers.yml"))

    out = capsys.readouterr().out

    assert "✓ Loaded metadata" in out
    assert "✓ Parsed 2 fields" in out
    assert "✓ Valid schema" in out
    assert "✓ No constraint violations" in out


def test_validate_invalid_spec_prints_failure(capsys):
    validate(_args("tests/fixtures/bad.yml"))

    out = capsys.readouterr().out

    assert "Validation failed" in out
    assert "banana" in out
    assert "✓" not in out


def test_validate_reports_both_hard_error_and_join_risk_warning(capsys):
    # A dataset can have a real error (unsupported type) AND the
    # join-risk pattern at once -- both must be reported, and the
    # warning must not be silently lost just because validate_table
    # also raised for the unrelated error.
    result = validate(_args("tests/fixtures/bad_with_join_risk.yml"))

    out = capsys.readouterr().out

    assert result is False  # command still exits nonzero
    assert "Validation failed" in out
    assert "banana" in out
    assert "1 warning(s)" in out
    assert "policy_status" in out
    assert "pick_one_order_by" in out


def test_validate_raw_csv_prints_clean_error_not_a_traceback(capsys):
    # The real reported bug: pointing validate at a raw-data CSV (no
    # column_name/type columns -- discover_csv()'s input shape, not
    # load_csv()'s) previously raised an unhandled KeyError straight
    # out of the CLI. load_csv() now raises ValueError for this,
    # which validate()'s existing except ValueError handling (already
    # proven for registry.py's unsupported-extension case) catches
    # exactly like any other bad-spec error -- no cli.py change needed.
    result = validate(_args("tests/fixtures/raw_customers.csv"))

    out = capsys.readouterr().out

    assert result is False
    assert "Validation failed" in out
    assert "does not appear to be a Structifact metadata CSV" in out
    assert "structifact discover" in out
    assert "Traceback" not in out
