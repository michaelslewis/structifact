import argparse

from structifact.cli import deps


def _args(paths):
    return argparse.Namespace(paths=paths)


def test_deps_valid_chain_prints_execution_order(capsys):
    deps(_args([
        "examples/dependency_demo/customers.yml",
        "examples/dependency_demo/transactions.yml",
        "examples/dependency_demo/customer_summary.yml",
        "examples/dependency_demo/daily_report.yml",
    ]))

    out = capsys.readouterr().out

    assert "✓ Loaded 4 dataset(s)" in out
    assert "--- EXECUTION ORDER ---" in out

    # Only dependency ordering is semantically significant — assert
    # relative positions of dependent datasets, not the exact line
    # numbers of customers/transactions relative to each other.
    lines = out.splitlines()
    customers_num = int(next(l for l in lines if l.endswith("customers")).split(".")[0])
    summary_num = int(next(l for l in lines if l.endswith("customer_summary")).split(".")[0])
    report_num = int(next(l for l in lines if l.endswith("daily_report")).split(".")[0])

    assert customers_num < summary_num < report_num


def test_deps_cyclic_prints_failure_not_execution_order(capsys):
    deps(_args([
        "examples/dependency_demo/cyclic_broken/dataset_a.yml",
        "examples/dependency_demo/cyclic_broken/dataset_b.yml",
        "examples/dependency_demo/cyclic_broken/dataset_c.yml",
    ]))

    out = capsys.readouterr().out

    assert "✓ Loaded 3 dataset(s)" in out
    assert "Dependency resolution failed" in out
    assert "Circular dependency detected" in out
    assert "EXECUTION ORDER" not in out


def test_deps_invalid_spec_prints_validation_failure(capsys):
    deps(_args(["tests/fixtures/bad.yml"]))

    out = capsys.readouterr().out

    assert "Validation failed for tests/fixtures/bad.yml" in out
    assert "banana" in out
    assert "EXECUTION ORDER" not in out
