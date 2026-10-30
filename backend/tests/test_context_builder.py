"""Tests for backend.app.services.context_builder.

Behaviour under test (s11 contract, from the implementation record):

- build_task_context(graph, task_id, workdir) -> TaskContext.
- The returned TaskContext.task and TaskContext.graph are an isolated
  deep-copy snapshot: mutating the caller's graph after the call does
  not affect the context, and neither object is the caller's object.
- A missing task raises ContextBuildError carrying the task_id.
- A str workdir is coerced to pathlib.Path.
- build_task_context does NOT validate the graph: an otherwise-invalid
  graph whose requested task resolves still builds. Validation is
  explicitly an upstream concern (validate_graph).

NOT EXECUTED in this session. Written against the s11 contract; see the
handoff note. Do not read prior session test counts as covering this file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.models.graph import (
    ArchitectureGraph,
    Edge,
    EdgeType,
    Node,
    NodeType,
    Task,
    TaskStatus,
)
from backend.app.services.coding_agent import TaskContext
from backend.app.services.context_builder import (
    ContextBuildError,
    build_task_context,
)


def _make_graph() -> ArchitectureGraph:
    """Small, valid, dependency-bearing graph used by most tests."""
    return ArchitectureGraph(
        project_name="context-builder-test",
        requirement="graph used to exercise build_task_context",
        nodes=[
            Node(id="svc-api", type=NodeType.SERVICE, name="API"),
            Node(id="db-main", type=NodeType.DATABASE, name="DB"),
        ],
        edges=[
            Edge(
                id="e-api-db",
                source="svc-api",
                target="db-main",
                type=EdgeType.DEPENDS_ON,
            ),
        ],
        tasks=[
            Task(id="task-api", node_id="svc-api", title="Build API"),
            Task(
                id="task-db",
                node_id="db-main",
                title="Provision DB",
                depends_on=["task-api"],
            ),
        ],
    )


def test_returns_task_context_for_existing_task():
    graph = _make_graph()
    ctx = build_task_context(graph, "task-api", "/tmp/work")

    assert isinstance(ctx, TaskContext)
    assert ctx.task.id == "task-api"
    assert ctx.task.title == "Build API"
    assert ctx.workdir == Path("/tmp/work")


def test_task_is_snapshot_not_original():
    graph = _make_graph()
    ctx = build_task_context(graph, "task-api", "/tmp/work")

    original_task = next(t for t in graph.tasks if t.id == "task-api")
    # Snapshot isolation is unconditional: the context must not hold the
    # caller's task object.
    assert ctx.task is not original_task


def test_context_graph_is_snapshot_not_original():
    graph = _make_graph()
    ctx = build_task_context(graph, "task-api", "/tmp/work")

    assert ctx.graph is not graph
    # Nested objects must be isolated too, not just the top-level graph.
    original_node = next(n for n in graph.nodes if n.id == "svc-api")
    original_node.name = "MUTATED-NAME"

    ctx_node = next(n for n in ctx.graph.nodes if n.id == "svc-api")
    assert ctx_node.name == "API"


def test_mutating_original_graph_after_build_does_not_affect_context():
    graph = _make_graph()
    ctx = build_task_context(graph, "task-api", "/tmp/work")

    # Mutate the caller's graph after the snapshot was taken.
    original_task = next(t for t in graph.tasks if t.id == "task-api")
    original_task.title = "MUTATED"
    original_task.status = TaskStatus.FAILED
    graph.tasks.append(Task(id="task-extra", node_id="svc-api", title="extra"))

    assert ctx.task.title == "Build API"
    assert ctx.task.status == TaskStatus.PENDING
    assert all(t.id != "task-extra" for t in ctx.graph.tasks)


def test_task_with_dependencies_and_evidence_lists_preserved():
    graph = ArchitectureGraph(
        project_name="p",
        nodes=[
            Node(id="svc-a", type=NodeType.SERVICE, name="A"),
            Node(id="svc-b", type=NodeType.SERVICE, name="B"),
        ],
        tasks=[
            Task(id="task-b", node_id="svc-b", title="B"),
            Task(
                id="task-a",
                node_id="svc-a",
                title="A",
                depends_on=["task-b"],
                execution_ids=["exec-1"],
                verification_ids=["ver-1"],
            ),
        ],
    )

    ctx = build_task_context(graph, "task-a", "/tmp/work")

    assert ctx.task.depends_on == ["task-b"]
    assert ctx.task.execution_ids == ["exec-1"]
    assert ctx.task.verification_ids == ["ver-1"]


def test_missing_task_raises_context_build_error():
    graph = _make_graph()

    with pytest.raises(ContextBuildError) as excinfo:
        build_task_context(graph, "task-does-not-exist", "/tmp/work")

    # ContextBuildError is constructed with the task_id; assert the id is
    # carried. Do NOT pin the message wording.
    assert excinfo.value.task_id == "task-does-not-exist"


def test_str_workdir_coerced_to_path():
    graph = _make_graph()
    ctx = build_task_context(graph, "task-api", "relative/dir")

    assert isinstance(ctx.workdir, Path)
    assert ctx.workdir == Path("relative/dir")


def test_build_does_not_validate_graph():
    # A dangling edge reference is an invalid graph per validate_graph, but
    # build_task_context must NOT validate: with a resolvable task it builds.
    graph = ArchitectureGraph(
        project_name="invalid-but-buildable",
        nodes=[Node(id="svc-a", type=NodeType.SERVICE, name="A")],
        edges=[
            Edge(
                id="e-bad",
                source="svc-a",
                target="does-not-exist",
                type=EdgeType.DEPENDS_ON,
            ),
        ],
        tasks=[Task(id="task-a", node_id="svc-a", title="A")],
    )

    ctx = build_task_context(graph, "task-a", "/tmp/work")
    assert ctx.task.id == "task-a"