"""
CLI exit-code and file-not-found error-handling contract.

Found during the 1.0 readiness audit by literally running the CLI as
a new user would (not by trusting the existing test suite, which
never checked process exit codes): every command handler caught its
expected errors, printed them, and returned -- with no sys.exit()
anywhere in cli.py, a genuine validation/execution/dependency failure
still exited 0. Separately, load_spec()/open() raising
FileNotFoundError (a very common real mistake -- a typo'd path) was
completely unhandled in most commands, producing a raw Python
traceback instead of a clean message.

Contract, now enforced: every command handler returns True on
success, False on a genuine failure (validation, missing file,
connection/execution/dependency error, etc.). main() converts a False
return into sys.exit(1); anything else (True, or an unaudited None)
exits 0. This file tests both the per-handler return-value contract
(matching this project's existing convention of calling handlers
directly with a constructed argparse.Namespace) and, once end to end,
that main() itself actually propagates that into a real process exit
code -- the two are different claims, and only the subprocess test
proves the second one.
"""

import argparse
import subprocess
import sys

from structifact.cli import (
    validate, validate_data, generate, deps, impact, execute, discover,
)


# ---------------------------------------------------------------------
# Real end-to-end proof that main() propagates a handler's False
# return into an actual nonzero process exit code -- the claim that
# matters, since a handler-level unit test alone can't prove main()
# is wired up correctly.
# ---------------------------------------------------------------------

def test_main_exits_nonzero_on_real_validation_failure():
    result = subprocess.run(
        [sys.executable, "-m", "structifact", "validate", "tests/fixtures/bad.yml"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "Validation failed" in result.stdout


def test_main_exits_zero_on_real_success():
    result = subprocess.run(
        [sys.executable, "-m", "structifact", "validate", "examples/customers/customers.yml"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0


def test_main_exits_nonzero_and_no_traceback_on_missing_file():
    result = subprocess.run(
        [sys.executable, "-m", "structifact", "execute", "/nonexistent/spec.yml", "--engine", "duckdb"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "File not found" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


# ---------------------------------------------------------------------
# Per-handler return-value contract: True on success, False on a
# genuine failure. Each handler tested with one success case (already
# covered for output content elsewhere -- just checking the return
# value here) and its FileNotFoundError path.
# ---------------------------------------------------------------------

def test_validate_returns_true_on_success(capsys):
    assert validate(argparse.Namespace(spec="tests/fixtures/customers.yml")) is True


def test_validate_returns_false_on_validation_failure(capsys):
    assert validate(argparse.Namespace(spec="tests/fixtures/bad.yml")) is False


def test_validate_returns_false_and_clean_message_on_missing_file(capsys):
    assert validate(argparse.Namespace(spec="/nonexistent/spec.yml")) is False
    assert "File not found" in capsys.readouterr().out


def test_generate_returns_false_on_missing_file(capsys):
    args = argparse.Namespace(spec="/nonexistent/spec.yml", output="output", generators=None)
    assert generate(args) is False
    assert "File not found" in capsys.readouterr().out


def test_deps_returns_false_on_missing_file(capsys):
    args = argparse.Namespace(paths=["/nonexistent/spec.yml"])
    assert deps(args) is False
    assert "File not found" in capsys.readouterr().out


def test_deps_returns_true_on_success(capsys, tmp_path):
    args = argparse.Namespace(paths=["tests/fixtures/customers.yml"])
    assert deps(args) is True


def test_impact_returns_false_on_missing_file(capsys):
    args = argparse.Namespace(dataset_name="customers", paths=["/nonexistent/spec.yml"])
    assert impact(args) is False
    assert "File not found" in capsys.readouterr().out


def test_execute_returns_false_on_missing_file(capsys):
    args = argparse.Namespace(
        spec="/nonexistent/spec.yml", engine="duckdb", connection=None,
        data=None, drop_if_exists=False, materialize=False,
    )
    assert execute(args) is False
    assert "File not found" in capsys.readouterr().out


def test_execute_returns_true_on_success(capsys, tmp_path):
    args = argparse.Namespace(
        spec="tests/fixtures/customers.yml", engine="duckdb",
        connection=str(tmp_path / "test.duckdb"), data=None,
        drop_if_exists=False, materialize=False,
    )
    assert execute(args) is True


def test_execute_returns_false_on_unknown_engine(capsys):
    args = argparse.Namespace(
        spec="tests/fixtures/customers.yml", engine="not_a_real_engine",
        connection=None, data=None, drop_if_exists=False, materialize=False,
    )
    assert execute(args) is False


def test_validate_data_returns_false_on_missing_schema(capsys):
    args = argparse.Namespace(spec="/nonexistent/spec.yml", data="tests/fixtures/customers.csv", ref=None)
    assert validate_data(args) is False
    assert "File not found" in capsys.readouterr().out


def test_discover_returns_false_on_missing_file(capsys):
    args = argparse.Namespace(spec="/nonexistent/data.csv", sample_size=100, ai=False, output=None)
    assert discover(args) is False
    assert "File not found" in capsys.readouterr().out
