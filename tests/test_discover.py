import argparse

from structifact.types import infer_type_from_values
from structifact.discover import discover_csv, render_draft_yaml
from structifact.adapters.yaml import load_yaml
from structifact.cli import discover as discover_cmd


# --- type inference ---

def test_infer_integer():
    assert infer_type_from_values(["1", "2", "3"]) == "integer"


def test_infer_decimal():
    assert infer_type_from_values(["1.5", "2", "3.25"]) == "decimal"


def test_infer_boolean():
    assert infer_type_from_values(["true", "false", "TRUE"]) == "boolean"


def test_infer_date():
    assert infer_type_from_values(["2024-01-15", "2024-02-20"]) == "date"


def test_infer_timestamp():
    assert infer_type_from_values(
        ["2024-01-15T10:30:00", "2024-02-20 08:00"]
    ) == "timestamp"


def test_infer_string_for_mixed_values():
    assert infer_type_from_values(["alice@example.com", "bob@example.com"]) == "string"


def test_infer_unknown_for_all_empty():
    assert infer_type_from_values(["", "", ""]) == "unknown"


def test_infer_ignores_blanks_when_checking_agreement():
    # blanks shouldn't stop the non-blank values from agreeing on a type
    assert infer_type_from_values(["1", "", "3"]) == "integer"


def test_infer_leading_zero_stays_string_not_integer():
    # int("001") == 1 works fine, but silently dropping the leading
    # zero would corrupt an identifier like a zip code or order id
    assert infer_type_from_values(["001", "002", "003"]) == "string"


def test_infer_recognizes_common_null_tokens():
    from structifact.types import is_null_token

    for token in ["", "  ", "NULL", "null", "N/A", "n/a", "-", "None"]:
        assert is_null_token(token) is True

    assert is_null_token("shipped") is False


def test_infer_type_excludes_null_tokens_from_agreement():
    # NULL/N/A shouldn't count as disagreeing "string" values that
    # break an otherwise-clean integer column
    assert infer_type_from_values(["1", "NULL", "3", "N/A"]) == "integer"


# --- messy real-world-shaped data ---

def test_discover_messy_csv_treats_leading_zero_ids_as_string():
    discovered = discover_csv("tests/fixtures/messy_orders.csv")
    by_name = {f.name: f for f in discovered.fields}

    assert by_name["order_id"].inferred_type == "string"
    assert by_name["zip_code"].inferred_type == "string"


def test_discover_messy_csv_counts_null_tokens_as_blank():
    discovered = discover_csv("tests/fixtures/messy_orders.csv")
    by_name = {f.name: f for f in discovered.fields}

    # notes has: "", "  ", "N/A", "NULL", "-", and one real value —
    # only the real value should count as non-blank
    assert by_name["notes"].null_count == 5


def test_discover_messy_csv_hints_at_currency_formatting():
    discovered = discover_csv("tests/fixtures/messy_orders.csv")
    by_name = {f.name: f for f in discovered.fields}

    assert by_name["amount"].inferred_type == "string"
    assert "currency" in by_name["amount"].format_hint


def test_discover_messy_csv_hints_at_inconsistent_date_formats():
    discovered = discover_csv("tests/fixtures/messy_orders.csv")
    by_name = {f.name: f for f in discovered.fields}

    assert by_name["order_date"].inferred_type == "string"
    assert "date" in by_name["order_date"].format_hint


# --- discover_csv ---

def test_discover_csv_infers_expected_columns():
    discovered = discover_csv("tests/fixtures/raw_customers.csv")

    assert discovered.name == "raw_customers"
    assert discovered.row_count == 4

    by_name = {f.name: f for f in discovered.fields}

    assert by_name["customer_id"].inferred_type == "integer"
    assert by_name["customer_id"].looks_unique is True
    assert by_name["customer_id"].nullable is False

    assert by_name["email"].inferred_type == "string"
    assert by_name["email"].looks_unique is True

    assert by_name["created_at"].inferred_type == "date"

    assert by_name["is_active"].inferred_type == "boolean"

    # "notes" has blanks and isn't unique/consistent-typed in a
    # meaningful way, but it should still be picked up as a column
    assert by_name["notes"].nullable is True


def test_discover_csv_respects_sample_size():
    discovered = discover_csv("tests/fixtures/raw_customers.csv", sample_size=2)

    # row_count reflects the whole file, but only 2 rows were sampled
    # per column
    assert discovered.row_count == 4

    by_name = {f.name: f for f in discovered.fields}
    assert by_name["customer_id"].sample_count == 2


# --- render_draft_yaml ---

def test_rendered_draft_is_marked_as_a_draft():
    discovered = discover_csv("tests/fixtures/raw_customers.csv")
    rendered = render_draft_yaml(discovered)

    assert "DRAFT" in rendered
    assert "review" in rendered.lower()


def test_rendered_draft_parses_with_the_real_yaml_adapter(tmp_path):
    discovered = discover_csv("tests/fixtures/raw_customers.csv")
    rendered = render_draft_yaml(discovered)

    draft_path = tmp_path / "draft.yml"
    draft_path.write_text(rendered)

    # The whole point of the draft format is that it's already valid
    # input to the existing, unmodified pipeline once a human accepts it.
    dataset = load_yaml(str(draft_path))

    assert dataset.name == "raw_customers"
    assert len(dataset.fields) == 5

    field_names = {f.name for f in dataset.fields}
    assert field_names == {
        "customer_id", "email", "created_at", "is_active", "notes"
    }


# --- CLI ---

def test_discover_cli_writes_draft_and_reports_summary(tmp_path, capsys):
    output_path = tmp_path / "out.yml"

    args = argparse.Namespace(
        spec="tests/fixtures/raw_customers.csv",
        output=str(output_path),
        sample_size=100,
    )

    discover_cmd(args)

    out = capsys.readouterr().out
    assert "✓ Read 4 row(s)" in out
    assert "✓ Inferred 5 column(s)" in out
    assert str(output_path) in out
    assert "draft" in out.lower()

    assert output_path.exists()
    assert "DRAFT" in output_path.read_text()


def test_discover_cli_rejects_non_csv(capsys):
    args = argparse.Namespace(
        spec="examples/customers.yml", output=None, sample_size=100
    )

    discover_cmd(args)

    out = capsys.readouterr().out
    assert "only supports raw CSV" in out
