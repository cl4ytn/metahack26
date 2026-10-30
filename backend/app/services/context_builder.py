"""Context building for GraphPilot coding-agent tasks.

Assembles the immutable ``TaskContext`` a coding agent receives when executing a
task. This module is pure: it never mutates the persisted graph and never
touches the filesystem. The returned context holds a deep-copied graph, so
downstream consumers cannot observe or mutate the caller's graph.

This module absorbs the private ``_build_context`` helper previously living in
``backend/app/api/tasks.py``. The migration in ``api/tasks.py`` is a separate
one-line change and is not performed here.
"""

from __future__ import annotations

from pathlib import Path

from backend.app.models.graph import ArchitectureGraph, Task
from backend.app.services.coding_agent import TaskContext

__all__ = ["ContextBuildError", "build_task_context"]


class ContextBuildError(Exception):
    """Raised when a ``TaskContext`` cannot be assembled.

    Currently raised only when the requested ``task_id`` is not present in the
    supplied graph. Callers are expected to translate this to an HTTP 404 (task
    not found) or equivalent; ``api/tasks.py`` already performs its own lookup
    before calling this module, so the common path never triggers it.
    """

    def __init__(self, task_id: str) -> None:
        super().__init__(f"task {task_id!r} not found in graph")
        self.task_id = task_id


def build_task_context(
    graph: ArchitectureGraph,
    task_id: str,
    workdir: Path | str,
) -> TaskContext:
    """Return a ``TaskContext`` snapshot for ``task_id``.

    The graph is deep-copied *before* the task lookup, so:

    - the returned ``TaskContext.graph`` is fully isolated from ``graph``;
    - the returned ``TaskContext.task`` is the copy inside that snapshot, not a
      reference into the caller's graph.

    ``workdir`` is coerced to ``Path``; its existence is not checked — the
    coding agent owns filesystem behaviour under it.

    Raises:
        ContextBuildError: if ``task_id`` is not present in ``graph``.
    """
    snapshot = graph.model_copy(deep=True)
    task = _find_task(snapshot, task_id)
    if task is None:
        raise ContextBuildError(task_id)
    return TaskContext(task=task, graph=snapshot, workdir=Path(workdir))


def _find_task(graph: ArchitectureGraph, task_id: str) -> Task | None:
    for task in graph.tasks:
        if task.id == task_id:
            return task
    return None