"""
examples/home_warranty_demo -- Structifact's flagship complex example
(home warranty claims coverage/reimbursement). Proves the real,
shipped example files -- not hand-constructed DatasetSpec objects --
actually execute correctly end to end against real DuckDB, matching
this project's established discipline that a passing unit test suite
against directly-constructed IR objects is not sufficient (see
DECISION_HISTORY.md's yaml.py source_table gap, found only by running
a real file through the real CLI).

Loads the four raw CSVs (via load_yaml() + real DuckDB, using DuckDB's
own NULLSTR-aware CSV reader for coverage_rules/claims -- see
README.md's "Genuine gaps found during the build" section for why:
Structifact's own `execute --data` path has no blank-cell-to-NULL
coercion, which breaks a typed DECIMAL column and, separately, lets a
blank required string column silently load as '' instead of NULL),
then runs ModelGenerator's real generated SQL and asserts exact
values for every claim with a defined expected outcome in the
handoff's Section 8, plus the two boundary claims (CL-09/CL-10) added
to actually exercise A3 (the 30-day window's inclusive boundary,
previously documented but never tested by the original 8 claims).

CL-07 (blank contractor_id) is deliberately excluded from the raw
`claims` table used here -- its own dedicated test
(test_validate_data_catches_cl07_blank_contractor_id) proves it's
caught by validate-data instead, matching the handoff's own statement
that CL-07 is "not expected to reach the transformation cleanly."
"""

import os
from decimal import Decimal

from structifact.adapters.yaml import load_yaml
from structifact.generators.model import ModelGenerator
from structifact.executors.duckdb import DuckDBExecutor
from structifact.quality import load_data_rows, check_data

EXAMPLE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "examples", "home_warranty_demo"
)


def _path(filename: str) -> str:
    return os.path.join(EXAMPLE_DIR, filename)


# claim_id -> (is_pre_existing_exclusion, is_covered, reimbursement_amount)
# From the handoff's Section 8, plus CL-09/CL-10 (the A3 boundary pair).
EXPECTED = {
    "CL-01": (False, True, "775.000"),
    "CL-02": (False, False, "0.000"),
    "CL-03": (False, True, "1150.000"),
    "CL-04": (False, True, "320.000"),
    "CL-05": (False, True, "220.000"),
    "CL-06": (False, True, "480.000"),
    "CL-08": (False, False, "0.000"),
    "CL-09": (True, False, "0.000"),   # day 30, inclusive boundary -- excluded
    "CL-10": (False, True, "525.000"),  # day 31 -- covered
}


def _load_raw_tables(executor: DuckDBExecutor) -> None:
    """
    Populates the four upstream tables `home_warranty_claims`'s model
    reads from -- via load_yaml() + real DDL for the clean sources
    (contracts, contractor_network), and DuckDB's own NULLSTR-aware
    CSV reader for the two sources with genuinely blank cells
    (coverage_rules' blank copay/cap, claims' blank contractor_id on
    CL-07) -- since Structifact's own execute --data path inserts a
    blank CSV cell as '', not SQL NULL, which breaks both a typed
    DECIMAL column and (separately) referential integrity against
    contractor_network for any downstream row carrying that ''.
    """
    from structifact.generators.sql import SQLGenerator

    for name in ("contracts", "contractor_network"):
        table = load_yaml(_path(f"{name}.yml"))
        executor.execute_ddl(SQLGenerator().generate(table).content)
        rows = load_data_rows(_path(f"{name}.csv"))
        executor.load_rows(table.name, [f.name for f in table.fields], rows)

    coverage_rules = load_yaml(_path("coverage_rules.yml"))
    executor.execute_ddl(SQLGenerator().generate(coverage_rules).content)
    executor.execute_ddl(
        f"COPY coverage_rules FROM '{_path('coverage_rules.csv')}' "
        f"(HEADER, NULLSTR '')"
    )

    claims = load_yaml(_path("claims.yml"))
    executor.execute_ddl(SQLGenerator().generate(claims).content)
    executor.execute_ddl(
        f"""
        INSERT INTO claims
        SELECT * FROM read_csv('{_path("claims.csv")}', header=true, nullstr='')
        WHERE contractor_id IS NOT NULL
        """
    )


def test_home_warranty_claims_model_produces_exact_expected_values():
    dataset = load_yaml(_path("home_warranty_claims.yml"))
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_tables(executor)

    result = executor.query(model_sql)
    executor.close()

    by_claim = {row["claim_id"]: row for row in result}

    assert set(by_claim) == set(EXPECTED), (
        "CL-07 must be absent (excluded upstream, see module docstring); "
        "every other claim in claims.csv must be present"
    )

    for claim_id, (expected_exclusion, expected_covered, expected_amount) in EXPECTED.items():
        row = by_claim[claim_id]
        assert row["is_pre_existing_exclusion"] == expected_exclusion, claim_id
        assert row["is_covered"] == expected_covered, claim_id
        assert row["reimbursement_amount"] == Decimal(expected_amount), claim_id


def test_c1001_dedup_picks_more_recently_entered_row():
    """
    A2 / Mess #2 -- contracts.csv has two C-1001 rows; the correct one
    (start_date 2025-03-01) is identified by record_entered_date, not
    by the larger start_date value (2025-03-10, the erroneous row).
    """
    dataset = load_yaml(_path("home_warranty_claims.yml"))
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_tables(executor)
    result = executor.query(model_sql)
    executor.close()

    c1001_claims = [row for row in result if row["claim_id"] in ("CL-01", "CL-05")]
    assert len(c1001_claims) == 2
    for row in c1001_claims:
        assert str(row["effective_date"]) == "2025-03-01"


def test_normalized_item_category_enables_coverage_match():
    """
    Mess #4 -- CL-03's item_category is "Water Heater" in claims.csv
    but coverage_rules.csv keys the same category as "WtrHtr". Without
    the normalization, the composite join would miss and CL-03 would
    be (wrongly) uncovered, same shape as CL-02's genuinely-missing-row
    case.
    """
    dataset = load_yaml(_path("home_warranty_claims.yml"))
    model_sql = ModelGenerator().generate(dataset).content

    executor = DuckDBExecutor()
    executor.connect()
    _load_raw_tables(executor)
    result = executor.query(model_sql)
    executor.close()

    cl03 = next(row for row in result if row["claim_id"] == "CL-03")
    assert cl03["normalized_item_category"] == "WtrHtr"
    assert cl03["is_covered"] is True
    assert cl03["reimbursement_amount"] == Decimal("1150.000")


def test_validate_data_catches_cl07_blank_contractor_id():
    """
    Mess #5 -- the required-field check runs against the real,
    unmodified claims.csv (all 10 rows, CL-07 included) via the
    dedicated raw claims schema, entirely independent of how the
    model-execution tests above populate their own `claims` table.
    """
    schema = load_yaml(_path("claims.yml"))
    rows = load_data_rows(_path("claims.csv"))

    result = check_data(schema, rows)

    required_issues = [issue for issue in result.issues if issue.rule == "required"]
    assert len(required_issues) == 1
    assert required_issues[0].field == "contractor_id"
    assert required_issues[0].rows == [7]  # CL-07 is data row 7
