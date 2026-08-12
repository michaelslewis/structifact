import pytest

from structifact.adapters.yaml import load_yaml
from structifact.ir import DatasetSpec, FieldSpec
from structifact.validation import validate_table
from structifact.dependencies import build_dependency_graph, execution_order


# ---------------------------------------------------------------------
# YAML adapter: parsing top-level depends_on
# ---------------------------------------------------------------------

def test_yaml_adapter_parses_depends_on(tmp_path):
    yaml_file = tmp_path / "customer_summary.yml"
    yaml_file.write_text(
        """
dataset:
  name: customer_summary

depends_on:
  - customers
  - transactions

fields:
  - name: customer_id
    type: string
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.depends_on == ["customers", "transactions"]


def test_yaml_adapter_depends_on_absent_defaults_to_empty_list():
    dataset = load_yaml("tests/fixtures/customers.yml")

    assert dataset.depends_on == []


def test_yaml_adapter_depends_on_does_not_collide_with_field_level_depends_on(tmp_path):
    """
    Dataset-level depends_on (top-level) and field-level depends_on
    (inside a computed field) are different concepts at different
    nesting levels — this confirms both parse independently and
    correctly in the same file.
    """
    yaml_file = tmp_path / "orders.yml"
    yaml_file.write_text(
        """
dataset:
  name: orders

depends_on:
  - customers

fields:
  - name: amount
    type: decimal(10,2)
  - name: doubled
    type: decimal(10,2)
    computed: true
    expression: "amount * 2"
    depends_on:
      - amount
"""
    )

    dataset = load_yaml(str(yaml_file))

    assert dataset.depends_on == ["customers"]
    assert dataset.fields[1].depends_on == ["amount"]


# ---------------------------------------------------------------------
# Per-dataset validation (validation.py) — blank / duplicate / self
# ---------------------------------------------------------------------

def test_validate_accepts_valid_depends_on():
    dataset = DatasetSpec(
        name="customer_summary",
        fields=[FieldSpec(name="customer_id", type="string")],
        depends_on=["customers", "transactions"],
    )

    validate_table(dataset)  # should not raise


def test_validate_ignores_depends_on_when_unset():
    dataset = DatasetSpec(
        name="customers",
        fields=[FieldSpec(name="customer_id", type="string")],
    )

    validate_table(dataset)  # should not raise


def test_validate_rejects_blank_depends_on_entry():
    dataset = DatasetSpec(
        name="customer_summary",
        fields=[FieldSpec(name="customer_id", type="string")],
        depends_on=["customers", ""],
    )

    with pytest.raises(ValueError, match="blank entry"):
        validate_table(dataset)


def test_validate_rejects_duplicate_depends_on_entry():
    dataset = DatasetSpec(
        name="customer_summary",
        fields=[FieldSpec(name="customer_id", type="string")],
        depends_on=["customers", "customers"],
    )

    with pytest.raises(ValueError, match="Duplicate entry in depends_on"):
        validate_table(dataset)


def test_validate_rejects_self_dependency():
    dataset = DatasetSpec(
        name="customer_summary",
        fields=[FieldSpec(name="customer_id", type="string")],
        depends_on=["customer_summary"],
    )

    with pytest.raises(ValueError, match="cannot depend on itself"):
        validate_table(dataset)


# ---------------------------------------------------------------------
# Collection-level graph building (dependencies.py)
# ---------------------------------------------------------------------

def _dataset(name, depends_on=None):
    return DatasetSpec(
        name=name,
        fields=[FieldSpec(name="id", type="string")],
        depends_on=depends_on or [],
    )


def test_build_graph_with_no_dependencies():
    datasets = [_dataset("customers"), _dataset("transactions")]

    graph = build_dependency_graph(datasets)

    assert graph == {"customers": [], "transactions": []}


def test_build_graph_with_one_dependency():
    datasets = [_dataset("customers"), _dataset("orders", ["customers"])]

    graph = build_dependency_graph(datasets)

    assert graph == {"customers": [], "orders": ["customers"]}


def test_build_graph_rejects_duplicate_dataset_names():
    datasets = [_dataset("customers"), _dataset("customers")]

    with pytest.raises(ValueError, match="Duplicate dataset name"):
        build_dependency_graph(datasets)


def test_build_graph_rejects_missing_referenced_dataset():
    datasets = [_dataset("orders", ["customers"])]  # customers not provided

    with pytest.raises(ValueError, match="not found in the provided collection"):
        build_dependency_graph(datasets)


def test_build_graph_reports_all_missing_references_together():
    datasets = [_dataset("orders", ["customers", "regions"])]

    with pytest.raises(ValueError) as exc_info:
        build_dependency_graph(datasets)

    message = str(exc_info.value)
    assert "customers" in message
    assert "regions" in message


# ---------------------------------------------------------------------
# Execution order — the four-dataset synthetic chain (acceptance example)
# ---------------------------------------------------------------------

def _dependency_chain_datasets():
    """
    The approved four-dataset acceptance fixture:

        customers ──────┐
                        ├──> customer_summary ──> daily_report
        transactions ───┘

    Tests fan-in (two roots into one dataset) and a chain depth of
    two levels, per the approved paper contract.
    """
    return [
        _dataset("customers"),
        _dataset("transactions"),
        _dataset("customer_summary", ["customers", "transactions"]),
        _dataset("daily_report", ["customer_summary"]),
    ]


def test_execution_order_respects_dependencies():
    order = execution_order(_dependency_chain_datasets())

    # Dependency ordering IS semantically significant and must hold.
    assert order.index("customers") < order.index("customer_summary")
    assert order.index("transactions") < order.index("customer_summary")
    assert order.index("customer_summary") < order.index("daily_report")


def test_execution_order_is_deterministic_across_repeated_calls():
    datasets = _dependency_chain_datasets()

    first = execution_order(datasets)
    second = execution_order(datasets)

    assert first == second


def test_execution_order_independent_datasets_relative_order_not_asserted():
    """
    Deliberately does NOT assert customers-before-transactions or
    vice versa — only that dependency constraints hold. Relative
    order between independent datasets is explicitly not part of the
    semantic contract (see execution_order()'s docstring).
    """
    order = execution_order(_dependency_chain_datasets())

    assert set(order) == {"customers", "transactions", "customer_summary", "daily_report"}


def test_execution_order_single_dataset_no_dependencies():
    order = execution_order([_dataset("customers")])

    assert order == ["customers"]


def test_execution_order_two_independent_datasets():
    order = execution_order([_dataset("customers"), _dataset("transactions")])

    assert set(order) == {"customers", "transactions"}


def test_execution_order_fan_out_one_dataset_feeds_multiple():
    """
    The inverse shape of fan-in: one dataset that multiple others
    depend on.
    """
    datasets = [
        _dataset("customers"),
        _dataset("customer_summary", ["customers"]),
        _dataset("customer_report", ["customers"]),
    ]

    order = execution_order(datasets)

    assert order.index("customers") < order.index("customer_summary")
    assert order.index("customers") < order.index("customer_report")


# ---------------------------------------------------------------------
# Cycle detection — the three-dataset cyclic acceptance fixture
# ---------------------------------------------------------------------

def test_execution_order_detects_simple_cycle():
    datasets = [
        _dataset("dataset_a", ["dataset_b"]),
        _dataset("dataset_b", ["dataset_c"]),
        _dataset("dataset_c", ["dataset_a"]),
    ]

    with pytest.raises(ValueError, match="Circular dependency detected"):
        execution_order(datasets)


def test_cycle_error_names_the_full_cycle():
    datasets = [
        _dataset("dataset_a", ["dataset_b"]),
        _dataset("dataset_b", ["dataset_c"]),
        _dataset("dataset_c", ["dataset_a"]),
    ]

    with pytest.raises(ValueError, match="dataset_a -> dataset_b -> dataset_c -> dataset_a"):
        execution_order(datasets)


def test_execution_order_detects_longer_cycle():
    datasets = [
        _dataset("a", ["d"]),
        _dataset("b", ["a"]),
        _dataset("c", ["b"]),
        _dataset("d", ["c"]),
    ]

    with pytest.raises(ValueError, match="Circular dependency detected"):
        execution_order(datasets)


def test_no_partial_order_returned_on_cycle():
    """
    A cycle must be a hard failure — no partial execution order
    should leak out via the exception or otherwise be usable.
    """
    datasets = [
        _dataset("dataset_a", ["dataset_c"]),
        _dataset("dataset_b", ["dataset_a"]),
        _dataset("dataset_c", ["dataset_b"]),
    ]

    with pytest.raises(ValueError):
        result = execution_order(datasets)
        # If we somehow got here without raising, fail explicitly —
        # there should be no reachable `result` at all.
        assert False, f"Expected ValueError, got order: {result}"


# ---------------------------------------------------------------------
# End-to-end acceptance: real YAML fixtures on disk
# ---------------------------------------------------------------------

def test_dependency_demo_example_end_to_end():
    """
    Loads the real, approved examples/dependency_demo/ fixtures
    (customers, transactions, customer_summary, daily_report) via
    load_yaml — the same acceptance example used throughout the
    paper-contract review — and confirms the full pipeline (YAML ->
    DatasetSpec -> validate_table -> execution_order) works end to
    end, not just against in-memory DatasetSpecs.
    """
    paths = [
        "examples/dependency_demo/customers.yml",
        "examples/dependency_demo/transactions.yml",
        "examples/dependency_demo/customer_summary.yml",
        "examples/dependency_demo/daily_report.yml",
    ]

    datasets = [load_yaml(p) for p in paths]

    for dataset in datasets:
        validate_table(dataset)  # should not raise

    order = execution_order(datasets)

    assert order.index("customers") < order.index("customer_summary")
    assert order.index("transactions") < order.index("customer_summary")
    assert order.index("customer_summary") < order.index("daily_report")


def test_dependency_demo_cyclic_broken_example_end_to_end():
    """
    Loads the real, approved examples/dependency_demo/cyclic_broken/
    fixtures and confirms the cycle is actually detected against
    real files on disk, not just constructed DatasetSpecs.
    """
    paths = [
        "examples/dependency_demo/cyclic_broken/dataset_a.yml",
        "examples/dependency_demo/cyclic_broken/dataset_b.yml",
        "examples/dependency_demo/cyclic_broken/dataset_c.yml",
    ]

    datasets = [load_yaml(p) for p in paths]

    with pytest.raises(ValueError, match="Circular dependency detected"):
        execution_order(datasets)
