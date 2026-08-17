import argparse

from structifact.cli import reconcile


def _args(old, new, mapping):
    return argparse.Namespace(old=old, new=new, mapping=mapping)


def test_reconcile_demo_prints_full_expected_report(capsys):
    reconcile(_args(
        "examples/reconciliation_demo/orders_legacy.yml:examples/reconciliation_demo/orders_legacy.csv",
        "examples/reconciliation_demo/orders_new.yml:examples/reconciliation_demo/orders_new.csv",
        "examples/reconciliation_demo/reconciliation.yml",
    ))

    out = capsys.readouterr().out

    assert "✓ Loaded schemas: orders_legacy (old), orders_new (new)" in out
    assert "✓ Loaded data: 5 old row(s), 5 new row(s)" in out
    assert "old: 5" in out
    assert "new: 5" in out
    assert "matched: 4" in out
    assert "✗ 3 issue(s) found" in out
    assert "missing_in_new: 1 row" in out
    assert "key=1004" in out
    assert "missing_in_old: 1 row" in out
    assert "key=1006" in out
    assert "order_amount: old_sum=485.50  new_sum=490.50  diff=+5.00" in out


def test_reconcile_identical_data_reports_no_issues(tmp_path, capsys):
    old_csv = tmp_path / "old.csv"
    old_csv.write_text("ORD_ID,ORD_AMT,ORD_DT\n1,10.00,2024-01-01\n")
    new_csv = tmp_path / "new.csv"
    new_csv.write_text("order_id,order_amount,order_date\n1,10.00,2024-01-01\n")

    reconcile(_args(
        f"examples/reconciliation_demo/orders_legacy.yml:{old_csv}",
        f"examples/reconciliation_demo/orders_new.yml:{new_csv}",
        "examples/reconciliation_demo/reconciliation.yml",
    ))

    out = capsys.readouterr().out

    assert "✓ No reconciliation issues found" in out


def test_reconcile_invalid_old_spec_prints_validation_failure(capsys):
    reconcile(_args(
        "tests/fixtures/bad.yml:examples/reconciliation_demo/orders_legacy.csv",
        "examples/reconciliation_demo/orders_new.yml:examples/reconciliation_demo/orders_new.csv",
        "examples/reconciliation_demo/reconciliation.yml",
    ))

    out = capsys.readouterr().out

    assert "Schema validation failed" in out
    assert "Row counts" not in out


def test_reconcile_missing_mapping_file_prints_file_not_found(capsys):
    reconcile(_args(
        "examples/reconciliation_demo/orders_legacy.yml:examples/reconciliation_demo/orders_legacy.csv",
        "examples/reconciliation_demo/orders_new.yml:examples/reconciliation_demo/orders_new.csv",
        "does_not_exist.yml",
    ))

    out = capsys.readouterr().out

    assert "File not found" in out
    assert "Row counts" not in out


def test_reconcile_malformed_old_argument_prints_error(capsys):
    reconcile(_args(
        "examples/reconciliation_demo/orders_legacy.yml",  # missing :data.csv
        "examples/reconciliation_demo/orders_new.yml:examples/reconciliation_demo/orders_new.csv",
        "examples/reconciliation_demo/reconciliation.yml",
    ))

    out = capsys.readouterr().out

    assert "expected format: schema.yml:data.csv" in out
