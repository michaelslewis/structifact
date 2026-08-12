"""
structifact/dependencies.py

Collection-level dependency resolution for Structifact datasets
(Phase 7 remainder — dataset dependency tracking).

This module is deliberately separate from validation.py, matching
the precedent set by quality.py: it operates on a COLLECTION of
DatasetSpecs (not a single one), which is a genuinely different
question than per-file metadata well-formedness.

Error-reporting style matches validate_table exactly: plain
ValueError, message built from an accumulated list of every problem
found (not just the first) wherever that's structurally possible —
duplicate names and missing references are collected together and
raised once. Cycle detection is necessarily a separate, later raise:
it requires a structurally sound graph (no duplicates, no missing
references) to even traverse.

Scope, explicit: this module represents and validates *that* one
dataset depends on another, and derives a safe processing order. It
does NOT resolve cross-dataset values, generate SQL, infer
dependencies from expressions, execute/materialize anything, or
support lineage/impact-analysis queries. Those are all real,
deferred capabilities, not implemented here.
"""

from typing import Dict, List

from .ir import DatasetSpec


def build_dependency_graph(datasets: List[DatasetSpec]) -> Dict[str, List[str]]:
    """
    Builds a {dataset_name: [depends_on names]} mapping from a
    collection of DatasetSpecs.

    Raises ValueError, listing every problem found, if:
    - two or more datasets in the collection share the same name
    - any depends_on entry names a dataset not present in the
      collection

    Does not detect cycles — that's execution_order()'s job, since
    cycle detection requires walking the graph, not just building it.
    """
    errors = []
    graph: Dict[str, List[str]] = {}

    for dataset in datasets:
        if dataset.name in graph:
            errors.append(
                f"Duplicate dataset name: '{dataset.name}' appears "
                "more than once in the provided collection."
            )
            continue
        graph[dataset.name] = list(dataset.depends_on)

    for name, deps in graph.items():
        for dep in deps:
            if dep not in graph:
                errors.append(
                    f"Dataset '{name}' depends on '{dep}', which was "
                    "not found in the provided collection."
                )

    if errors:
        raise ValueError("\n".join(errors))

    return graph


def execution_order(datasets: List[DatasetSpec]) -> List[str]:
    """
    Returns a deterministic execution order for the given collection
    of DatasetSpecs: every dataset name appears after all of its
    (direct and transitive) dependencies.

    IMPORTANT: the relative order of two datasets that don't depend
    on each other, directly or transitively, is NOT semantically
    meaningful — Structifact only guarantees dependency ordering is
    respected. Output is nonetheless deterministic (stable given the
    same input list, tie-broken by input order) so tests, logs, and
    generated output don't vary run-to-run.

    Raises ValueError (no partial order returned) if:
    - build_dependency_graph() would raise (duplicate name / unresolved
      reference — message lists every such problem)
    - a circular dependency exists — the message names the full
      cycle, e.g. "Circular dependency detected: dataset_a ->
      dataset_b -> dataset_c -> dataset_a"
    """
    graph = build_dependency_graph(datasets)
    input_order = [dataset.name for dataset in datasets]

    order: List[str] = []
    visited = set()       # fully processed, already in `order`
    in_progress = set()   # currently on the current DFS path (cycle check)

    def visit(name: str, path: List[str]) -> None:
        if name in visited:
            return
        if name in in_progress:
            cycle = path[path.index(name):] + [name]
            raise ValueError(
                "Circular dependency detected: " + " -> ".join(cycle)
            )

        in_progress.add(name)
        for dep in graph[name]:
            visit(dep, path + [name])
        in_progress.remove(name)

        visited.add(name)
        order.append(name)

    for name in input_order:
        visit(name, [])

    return order
