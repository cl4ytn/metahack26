"""Deterministic scheduling over an approved ArchitectureGraph.

Pure: no I/O, no mutation, no model/agent/test calls. The scheduler returns a
plan; the caller (orchestration) applies status transitions. It never
produces `verified` or any other evidence-dependent status.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.models.graph import ArchitectureGraph, GraphStatus, TaskStatus
from backend.app.services.validator import ValidationReport, validate_graph

# Tasks the scheduler classifies. All other statuses are left alone.
_SCHEDULABLE = frozenset({TaskStatus.PENDING, TaskStatus.READY, TaskStatus.BLOCKED})
# Dependency statuses that block their dependants.
_BLOCKING = frozenset({TaskStatus.FAILED})


class SchedulerError(Exception):
    """Base class for scheduler failures."""


class UnschedulableGraphError(SchedulerError):
    """The graph failed validate_graph; nothing was scheduled."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__("graph failed validation and cannot be scheduled")
        self.report = report


class GraphNotApprovedError(SchedulerError):
    """Only approved graphs are schedulable."""

    def __init__(self, status: object) -> None:
        super().__init__(f"graph status is {status!r}; only 'approved' graphs can be scheduled")
        self.status = status


@dataclass(frozen=True)
class SchedulePlan:
    """Task ids per outcome, each in task declaration order.

    ready:   pending/ready tasks whose dependencies are all verified.
    blocked: pending/ready tasks with a failed/blocked dependency
             (transitively). Caller should set these to `blocked`.
    waiting: pending/ready tasks that are neither ready nor blocked.
    """

    ready: tuple[str, ...]
    blocked: tuple[str, ...]
    waiting: tuple[str, ...]


def build_schedule(graph: ArchitectureGraph) -> SchedulePlan:
    """Classify schedulable tasks. Raises SchedulerError subclasses on refusal."""
    report = validate_graph(graph)
    if not report.is_valid:
        raise UnschedulableGraphError(report)
    if graph.status != GraphStatus.APPROVED:
        raise GraphNotApprovedError(graph.status)

    status = {task.id: task.status for task in graph.tasks}
    candidates = [task for task in graph.tasks if task.status in _SCHEDULABLE]

    # Propagate blocking to a fixpoint (graph is acyclic, so this terminates).
    blocked: set[str] = set()
    changed = True
    while changed:
        changed = False
        for task in candidates:
            if task.id in blocked:
                continue
            if any(status[d] in _BLOCKING or d in blocked for d in task.depends_on):
                blocked.add(task.id)
                changed = True

    ready: list[str] = []
    waiting: list[str] = []
    blocked_ordered: list[str] = []
    for task in candidates:
        if task.id in blocked:
            blocked_ordered.append(task.id)
        elif all(status[d] == TaskStatus.VERIFIED for d in task.depends_on):
            ready.append(task.id)
        else:
            waiting.append(task.id)

    return SchedulePlan(
        ready=tuple(ready),
        blocked=tuple(blocked_ordered),
        waiting=tuple(waiting),
    )

def reconcile_schedule(graph: ArchitectureGraph) -> ArchitectureGraph:
    """Apply canonical scheduling including blocked-task recovery."""
    if graph.status != GraphStatus.APPROVED:
        return graph.model_copy(update={"tasks": [t.model_copy(update={"status": TaskStatus.PENDING}) for t in graph.tasks]})
    plan = build_schedule(graph)
    states = {**dict.fromkeys(plan.ready, TaskStatus.READY), **dict.fromkeys(plan.blocked, TaskStatus.BLOCKED), **dict.fromkeys(plan.waiting, TaskStatus.PENDING)}
    return graph.model_copy(update={"tasks": [t.model_copy(update={"status": states[t.id]}) if t.id in states else t for t in graph.tasks]})
