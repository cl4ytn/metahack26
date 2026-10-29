"""Independent graph-integrity validation for GraphPilot.

This module answers one question: "is this ArchitectureGraph internally
consistent?" It does not load, save, repair, schedule or call any model.

Public interface:

    report = validate_graph(graph)
    report.is_valid        # bool
    report.errors          # list[ValidationIssue], every problem found

Design rules:
- Pure function. The graph is only read, never modified or "fixed".
- All problems are collected; validation never stops at the first one.
- Order of errors is deterministic (check order, then document order).
- Enum members are compared by value ("verified", "approved") so this module
  does not depend on how the enum members are spelled in graph.py.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field as dc_field
from typing import Any

from backend.app.models.graph import ArchitectureGraph

# Stable machine-readable issue codes (the API/frontend may branch on these).
DUPLICATE_ID = "duplicate_id"
UNRESOLVED_REFERENCE = "unresolved_reference"
EVIDENCE_MISMATCH = "evidence_mismatch"
SELF_DEPENDENCY = "self_dependency"
DEPENDENCY_CYCLE = "dependency_cycle"
VERIFIED_WITHOUT_EVIDENCE = "verified_without_passing_verification"
APPROVED_WITH_ISSUES = "approved_with_issues"


@dataclass(frozen=True)
class ValidationIssue:
    """One integrity problem: what is wrong, where, and which ID is involved."""

    code: str
    message: str
    entity_type: str  # node | edge | task | execution | verification | graph
    entity_id: str | None = None  # the entity that contains the problem
    field: str | None = None  # e.g. "depends_on[1]"
    ref_id: str | None = None  # the offending referenced ID, if any

    def __str__(self) -> str:
        return self.message


@dataclass
class ValidationReport:
    errors: list[ValidationIssue] = dc_field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def messages(self) -> list[str]:
        return [e.message for e in self.errors]


def validate_graph(graph: ArchitectureGraph) -> ValidationReport:
    """Check graph integrity and return every problem found."""
    index = _Index(graph)
    issues: list[ValidationIssue] = []
    issues += _check_duplicate_ids(graph)
    issues += _check_references(graph, index)
    issues += _check_evidence_links(graph, index)
    issues += _check_task_dependencies(graph, index)
    issues += _check_verified_tasks(graph, index)

    # Last, so the count covers everything above.
    if _value(graph.status) == "approved" and issues:
        issues.append(
            ValidationIssue(
                code=APPROVED_WITH_ISSUES,
                message=(
                    f"graph status is 'approved' but it has {len(issues)} "
                    "integrity issue(s); an approved graph must be valid"
                ),
                entity_type="graph",
                field="status",
            )
        )
    return ValidationReport(errors=issues)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _value(x: Any) -> Any:
    """Enum member -> its value; plain values pass through unchanged."""
    return getattr(x, "value", x)


def _group(items: Any) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for item in items:
        out.setdefault(item.id, []).append(item)
    return out


class _Index:
    """Lookup tables built once. Duplicate IDs keep every record."""

    def __init__(self, graph: ArchitectureGraph) -> None:
        self.node_ids = {n.id for n in graph.nodes}
        self.task_ids = {t.id for t in graph.tasks}
        self.executions = _group(graph.executions)
        self.verifications = _group(graph.verifications)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def _check_duplicate_ids(graph: ArchitectureGraph) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    collections = (
        ("node", graph.nodes),
        ("edge", graph.edges),
        ("task", graph.tasks),
        ("execution", graph.executions),
        ("verification", graph.verifications),
    )
    for entity_type, items in collections:
        for entity_id, count in Counter(i.id for i in items).items():
            if count > 1:
                issues.append(
                    ValidationIssue(
                        code=DUPLICATE_ID,
                        message=(
                            f"{entity_type} id '{entity_id}' appears {count} "
                            f"times; ids must be unique among {entity_type}s"
                        ),
                        entity_type=entity_type,
                        entity_id=entity_id,
                        field="id",
                    )
                )
    return issues


def _check_references(
    graph: ArchitectureGraph, index: _Index
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def check(
        entity_type: str,
        entity_id: str,
        field: str,
        ref: str | None,
        target_type: str,
        valid: Any,
    ) -> None:
        if ref is None or ref in valid:
            return
        issues.append(
            ValidationIssue(
                code=UNRESOLVED_REFERENCE,
                message=(
                    f"{entity_type} '{entity_id}': {field} references "
                    f"unknown {target_type} '{ref}'"
                ),
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                ref_id=ref,
            )
        )

    for edge in graph.edges:
        check("edge", edge.id, "source", edge.source, "node", index.node_ids)
        check("edge", edge.id, "target", edge.target, "node", index.node_ids)

    for task in graph.tasks:
        check("task", task.id, "node_id", task.node_id, "node", index.node_ids)
        for i, ref in enumerate(task.depends_on):
            check("task", task.id, f"depends_on[{i}]", ref, "task", index.task_ids)
        for i, ref in enumerate(task.execution_ids):
            check(
                "task", task.id, f"execution_ids[{i}]", ref,
                "execution", index.executions,
            )
        for i, ref in enumerate(task.verification_ids):
            check(
                "task", task.id, f"verification_ids[{i}]", ref,
                "verification", index.verifications,
            )

    for ex in graph.executions:
        check("execution", ex.id, "task_id", ex.task_id, "task", index.task_ids)

    for ver in graph.verifications:
        check("verification", ver.id, "task_id", ver.task_id, "task", index.task_ids)
        check(
            "verification", ver.id, "execution_id", ver.execution_id,
            "execution", index.executions,
        )
    return issues


def _check_evidence_links(
    graph: ArchitectureGraph, index: _Index
) -> list[ValidationIssue]:
    """Evidence that resolves must also belong to the task that claims it."""
    issues: list[ValidationIssue] = []

    for task in graph.tasks:
        for field, ids, table, label in (
            ("execution_ids", task.execution_ids, index.executions, "execution"),
            ("verification_ids", task.verification_ids, index.verifications,
             "verification"),
        ):
            for i, ref in enumerate(ids):
                records = table.get(ref)
                if records and all(r.task_id != task.id for r in records):
                    issues.append(
                        ValidationIssue(
                            code=EVIDENCE_MISMATCH,
                            message=(
                                f"task '{task.id}': {field}[{i}] {label} "
                                f"'{ref}' belongs to task "
                                f"'{records[0].task_id}', not '{task.id}'"
                            ),
                            entity_type="task",
                            entity_id=task.id,
                            field=f"{field}[{i}]",
                            ref_id=ref,
                        )
                    )

    for ver in graph.verifications:
        if ver.execution_id is None:
            continue
        records = index.executions.get(ver.execution_id)
        if records and all(r.task_id != ver.task_id for r in records):
            issues.append(
                ValidationIssue(
                    code=EVIDENCE_MISMATCH,
                    message=(
                        f"verification '{ver.id}': execution_id "
                        f"'{ver.execution_id}' belongs to task "
                        f"'{records[0].task_id}' but the verification is for "
                        f"task '{ver.task_id}'"
                    ),
                    entity_type="verification",
                    entity_id=ver.id,
                    field="execution_id",
                    ref_id=ver.execution_id,
                )
            )
    return issues


def _check_task_dependencies(
    graph: ArchitectureGraph, index: _Index
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # adj[a] = tasks that `a` depends on. Only resolvable, non-self edges are
    # kept: dangling refs and self-loops are reported by their own checks.
    adj: dict[str, list[str]] = {tid: [] for tid in index.task_ids}
    for task in graph.tasks:
        for i, dep in enumerate(task.depends_on):
            if dep == task.id:
                issues.append(
                    ValidationIssue(
                        code=SELF_DEPENDENCY,
                        message=f"task '{task.id}' depends on itself",
                        entity_type="task",
                        entity_id=task.id,
                        field=f"depends_on[{i}]",
                        ref_id=dep,
                    )
                )
            elif dep in index.task_ids and dep not in adj[task.id]:
                adj[task.id].append(dep)

    components = [c for c in _strongly_connected_components(adj) if len(c) > 1]
    components.sort(key=min)
    for component in components:
        members = set(component)
        start = min(members)
        path = _cycle_path(start, members, adj)
        text = " -> ".join(path)
        extra = sorted(members - set(path))
        if extra:
            text += f" (also entangled: {', '.join(extra)})"
        issues.append(
            ValidationIssue(
                code=DEPENDENCY_CYCLE,
                message=(
                    f"task dependency cycle: {text} "
                    "(each task depends on the next)"
                ),
                entity_type="task",
                entity_id=start,
                field="depends_on",
            )
        )
    return issues


def _strongly_connected_components(adj: dict[str, list[str]]) -> list[list[str]]:
    """Iterative Tarjan SCC (no recursion, so long chains cannot overflow)."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    for root in sorted(adj):
        if root in index_of:
            continue
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(adj[root]))]
        while work:
            node, neighbours = work[-1]
            descended = False
            for nxt in neighbours:
                if nxt not in index_of:
                    index_of[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(adj[nxt])))
                    descended = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                result.append(component)
    return result


def _cycle_path(start: str, members: set[str], adj: dict[str, list[str]]) -> list[str]:
    """Shortest concrete cycle through `start` inside one SCC: [start, ..., start]."""
    parent: dict[str, str | None] = {start: None}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for nxt in adj[node]:
            if nxt not in members:
                continue
            if nxt == start:
                path = [node]
                while parent[path[-1]] is not None:
                    path.append(parent[path[-1]])  # type: ignore[arg-type]
                path.reverse()
                return path + [start]
            if nxt not in parent:
                parent[nxt] = node
                queue.append(nxt)
    return sorted(members)  # pragma: no cover - an SCC of size > 1 always has a cycle


def _check_verified_tasks(
    graph: ArchitectureGraph, index: _Index
) -> list[ValidationIssue]:
    """`verified` needs a passing result that is in the graph, listed by the
    task, and recorded for that same task. The agent's claim never counts."""
    issues: list[ValidationIssue] = []
    for task in graph.tasks:
        if _value(task.status) != "verified":
            continue
        has_evidence = any(
            ver.passed and ver.task_id == task.id
            for vid in task.verification_ids
            for ver in index.verifications.get(vid, [])
        )
        if not has_evidence:
            issues.append(
                ValidationIssue(
                    code=VERIFIED_WITHOUT_EVIDENCE,
                    message=(
                        f"task '{task.id}' has status 'verified' but no passing "
                        f"verification for it is recorded in the graph "
                        f"(verification_ids={list(task.verification_ids)}); a "
                        f"passing result must be listed in verification_ids and "
                        f"have task_id '{task.id}'"
                    ),
                    entity_type="task",
                    entity_id=task.id,
                    field="status",
                )
            )
    return issues