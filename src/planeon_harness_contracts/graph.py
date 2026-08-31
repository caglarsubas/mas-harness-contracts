"""Deterministic closure and topological-wave algorithms."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from planeon_harness_contracts.errors import CompilationError


def validate_graph(nodes: Iterable[str], dependencies: Mapping[str, Iterable[str]]) -> None:
    """Reject unknown nodes, self edges, and cycles in a closed dependency graph."""

    node_set = frozenset(nodes)
    for source in sorted(dependencies):
        if source not in node_set:
            raise CompilationError(
                "CLOSURE_INCOMPLETE",
                "dependency graph contains an unknown source",
                {"source": source},
            )
        for target in sorted(set(dependencies[source])):
            if target not in node_set:
                raise CompilationError(
                    "CLOSURE_INCOMPLETE",
                    "dependency graph contains an unknown target",
                    {"source": source, "target": target},
                )
            if target == source:
                raise CompilationError(
                    "DEPENDENCY_CYCLE",
                    "dependency graph contains a self edge",
                    {"cycle": [source, source]},
                )
    topological_waves(node_set, dependencies)


def transitive_closure(
    seeds: Iterable[str],
    dependencies: Mapping[str, Iterable[str]],
) -> tuple[str, ...]:
    """Return deterministic prerequisite closure for validated seed nodes."""

    known = frozenset(dependencies)
    selected = set(seeds)
    unknown = selected - known
    if unknown:
        raise CompilationError(
            "CLOSURE_INCOMPLETE",
            "closure seed is absent from the graph",
            {"resourceIds": sorted(unknown)},
        )
    pending = list(sorted(selected))
    while pending:
        source = pending.pop(0)
        for target in sorted(set(dependencies[source])):
            if target not in known:
                raise CompilationError(
                    "CLOSURE_INCOMPLETE",
                    "dependency target is absent from the graph",
                    {"source": source, "target": target},
                )
            if target not in selected:
                selected.add(target)
                pending.append(target)
                pending.sort()
    topological_waves(selected, dependencies)
    return tuple(sorted(selected))


def topological_waves(
    nodes: Iterable[str],
    dependencies: Mapping[str, Iterable[str]],
) -> tuple[tuple[str, ...], ...]:
    """Return dependency-first lexical waves or a stable cycle error."""

    remaining = set(nodes)
    closed: dict[str, set[str]] = {}
    for node in remaining:
        if node not in dependencies:
            raise CompilationError(
                "CLOSURE_INCOMPLETE",
                "topological node has no dependency declaration",
                {"resourceId": node},
            )
        targets = set(dependencies[node])
        outside = targets - remaining
        if outside:
            raise CompilationError(
                "CLOSURE_INCOMPLETE",
                "selected closure omits a required dependency",
                {"resourceId": node, "missingResourceIds": sorted(outside)},
            )
        closed[node] = targets
    waves: list[tuple[str, ...]] = []
    installed: set[str] = set()
    while remaining:
        wave = tuple(
            sorted(node for node in remaining if closed[node].issubset(installed))
        )
        if not wave:
            cycle_nodes = sorted(remaining)
            raise CompilationError(
                "DEPENDENCY_CYCLE",
                "dependency graph contains a cycle",
                {"resourceIds": cycle_nodes},
            )
        waves.append(wave)
        installed.update(wave)
        remaining.difference_update(wave)
    return tuple(waves)
