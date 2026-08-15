import argparse

from structifact.cli import impact


def _args(dataset_name, paths):
    return argparse.Namespace(dataset_name=dataset_name, paths=paths)


def test_impact_root_dataset_prints_downstream_datasets(capsys):
    impact(_args("customers", [
        "examples/dependency_demo/customers.yml",
        "examples/dependency_demo/transactions.yml",
        "examples/dependency_demo/customer_summary.yml",
        "examples/dependency_demo/daily_report.yml",
    ]))

    out = capsys.readouterr().out

    assert "✓ Loaded 4 dataset(s)" in out
    assert "--- IMPACTED BY 'customers' ---" in out
    assert "1. customer_summary" in out
    assert "2. daily_report" in out


def test_impact_terminal_dataset_prints_no_dependents_message(capsys):
    impact(_args("daily_report", [
        "examples/dependency_demo/customers.yml",
        "examples/dependency_demo/transactions.yml",
        "examples/dependency_demo/customer_summary.yml",
        "examples/dependency_demo/daily_report.yml",
    ]))

    out = capsys.readouterr().out

    assert "✓ Loaded 4 dataset(s)" in out
    assert "--- IMPACTED BY 'daily_report' ---" in out
    assert "(no datasets depend on 'daily_report')" in out


def test_impact_unknown_dataset_name_prints_failure(capsys):
    impact(_args("nonexistent", [
        "examples/dependency_demo/customers.yml",
        "examples/dependency_demo/transactions.yml",
        "examples/dependency_demo/customer_summary.yml",
        "examples/dependency_demo/daily_report.yml",
    ]))

    out = capsys.readouterr().out

    assert "✓ Loaded 4 dataset(s)" in out
    assert "Dependency resolution failed" in out
    assert "'nonexistent' was not found in the provided collection" in out
    assert "IMPACTED BY" not in out


def test_impact_cyclic_prints_failure_not_impact_report(capsys):
    impact(_args("dataset_a", [
        "examples/dependency_demo/cyclic_broken/dataset_a.yml",
        "examples/dependency_demo/cyclic_broken/dataset_b.yml",
        "examples/dependency_demo/cyclic_broken/dataset_c.yml",
    ]))

    out = capsys.readouterr().out

    assert "✓ Loaded 3 dataset(s)" in out
    assert "Dependency resolution failed" in out
    assert "Circular dependency detected" in out
    assert "IMPACTED BY" not in out


def test_impact_invalid_spec_prints_validation_failure(capsys):
    impact(_args("customers", ["tests/fixtures/bad.yml"]))

    out = capsys.readouterr().out

    assert "Validation failed for tests/fixtures/bad.yml" in out
    assert "banana" in out
    assert "IMPACTED BY" not in out
