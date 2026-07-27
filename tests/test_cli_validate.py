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
