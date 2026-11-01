"""Muse Spark adapter interface and a replayed fixture implementation.

Muse Spark is the component that turns a natural-language requirement into an
`ArchitectureGraph` and that refines an existing draft graph when the user
follows up with a modification instruction. The real Muse Spark service is NOT
available to the GraphPilot demo and its request/response shapes are unknown,
so this module defines only the narrow Python-level contract plus a fixture
that replays fixed edits.

Nothing here invents an HTTP endpoint, a JSON payload, a prompt, or a model
response shape. A real adapter can implement `MuseSparkAdapter` later without
touching any other module.

The fixture is a REPLAY, not a model call. Its class name, its log output, and
every place it is surfaced must say so.

Contract
--------
`MuseSparkAdapter.generate_graph(requirement) -> ArchitectureGraph` produces a
DRAFT graph. `MuseSparkAdapter.refine_graph(current, instruction) ->
ArchitectureGraph` produces a new DRAFT graph from an existing one, appending
exactly one `RefinementTurn` to `refinement_history`. Neither method validates
graph semantics or approves anything: callers must run `validate_graph` and
obtain user approval before persistence or execution.

``refine_graph`` must not mutate ``current``. It requires a 1.1 schema input;
a 1.0 graph must be regenerated via ``generate_graph`` first.
"""

from __future__ import annotations

import logging
import re
from typing import Protocol, runtime_checkable

from backend.app.models.graph import (
    ArchitectureGraph,
    Edge,
    EdgeType,
    Node,
    NodeType,
    RefinementTurn,
    Task,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FIXTURE_NAME",
    "FixtureMuseSpark",
    "MuseSparkAdapter",
    "MuseSparkError",
    "MuseSparkOutputError",
    "MuseSparkUnavailableError",
]

FIXTURE_NAME = "muse-spark-fixture-replay"


# --- error vocabulary -------------------------------------------------------
# Real adapters raise these; the API layer can catch `MuseSparkError` once and
# map it to a single failure response. The fixture raises them only for
# instructions it does not understand or for input it refuses (bad schema,
# unknown entity, collision).

class MuseSparkError(Exception):
    """Base class for every Muse Spark adapter failure."""


class MuseSparkUnavailableError(MuseSparkError):
    """The adapter could not produce a graph at all (service down, timeout)."""


class MuseSparkOutputError(MuseSparkError):
    """The adapter produced output that could not be turned into a graph."""


# --- enum values ------------------------------------------------------------
# graph.py declares lowercase string values for its enums. Members are looked
# up by VALUE so this module does not depend on how the members happen to be
# named (NodeType.API vs NodeType.api). Change nothing if the names differ.

_NODE_API = NodeType("api")
_NODE_SERVICE = NodeType("service")
_NODE_MODULE = NodeType("module")
_NODE_DATABASE = NodeType("database")
_NODE_UI = NodeType("ui")

_EDGE_CALLS = EdgeType("calls")
_EDGE_DEPENDS_ON = EdgeType("depends_on")


# --- instruction patterns (fixture only) ------------------------------------
# These are substring matches on the instruction text. They are NOT language
# understanding: the fixture is a replay, and these patterns are its script.

_ADD_AUTH_RE = re.compile(r"^add\s+(auth|authentication)$", re.IGNORECASE)
_REMOVE_RE = re.compile(r"^remove\s+(\S+)$", re.IGNORECASE)
_RENAME_RE = re.compile(r"^rename\s+(\S+)\s+to\s+(\S+)$", re.IGNORECASE)
_ENTITY_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


# --- interface --------------------------------------------------------------

@runtime_checkable
class MuseSparkAdapter(Protocol):
    """Requirement text in, `ArchitectureGraph` out. The only contract.

    Implementations must be interchangeable. They must not leak transport
    details (URLs, payload keys, model names) into their return value.
    """

    def name(self) -> str:
        """Stable identifier for logs, API responses and the demo."""

    def is_fixture(self) -> bool:
        """True when the output is replayed rather than produced by a model."""

    def generate_graph(self, requirement: str) -> ArchitectureGraph:
        """Turn requirement text into a draft graph. Blocking call."""

    def refine_graph(
        self, current: ArchitectureGraph, instruction: str
    ) -> ArchitectureGraph:
        """Produce a new draft graph from ``current`` per the instruction.

        Must not mutate ``current``. Must append exactly one
        ``RefinementTurn`` to the returned graph's ``refinement_history``.
        Requires a 1.1 input graph.
        """


# --- replayed fixture -------------------------------------------------------

class FixtureMuseSpark:
    """Replayed Muse Spark stand-in. NOT a model call.

    ``generate_graph`` returns the same fixed architecture graph on every call.
    ``refine_graph`` applies a small set of scripted edits matched on the
    instruction text: add the auth service, remove a task or node (cascading
    to dependents), or rename a task or node (updating references in place).
    Every edit is recorded as one ``RefinementTurn``.
    """

    def name(self) -> str:
        return FIXTURE_NAME

    def is_fixture(self) -> bool:
        return True

    def generate_graph(self, requirement: str) -> ArchitectureGraph:
        text = (requirement or "").strip()
        if not text:
            raise ValueError(
                "FixtureMuseSpark.generate_graph() requires a non-empty "
                "requirement string"
            )

        logger.info(
            "Muse Spark FIXTURE (replayed): returning a fixed architecture "
            "graph for %d characters of requirement text. No model call was "
            "made and no real Muse Spark API was contacted.",
            len(text),
        )
        return _build_fixture_graph(text)

    def refine_graph(
        self, current: ArchitectureGraph, instruction: str
    ) -> ArchitectureGraph:
        if current.schema_version != "1.1":
            raise MuseSparkOutputError(
                f"refine_graph requires schema_version '1.1'; got "
                f"{current.schema_version!r}. Regenerate the graph via "
                f"generate_graph() before refining."
            )

        text = (instruction or "").strip()
        if not text:
            raise ValueError(
                "FixtureMuseSpark.refine_graph() requires a non-empty "
                "instruction"
            )

        result = current.model_copy(deep=True)

        if _ADD_AUTH_RE.match(text):
            turn = _apply_add_auth(result)
        elif (m := _REMOVE_RE.match(text)):
            turn = _apply_remove(result, m.group(1))
        elif (m := _RENAME_RE.match(text)):
            turn = _apply_rename(result, m.group(1), m.group(2))
        else:
            raise MuseSparkOutputError(
                f"fixture refine does not understand instruction {text!r}; "
                "supported: 'add auth', 'remove <id>', 'rename <old> to <new>'"
            )

        result.refinement_history = list(current.refinement_history) + [turn]

        logger.info(
            "Muse Spark FIXTURE (replayed): refined graph per instruction %r. "
            "No model call was made and no real Muse Spark API was contacted.",
            text,
        )
        return result


def _build_fixture_graph(requirement: str) -> ArchitectureGraph:
    """Build a fresh copy of the fixed fixture graph.

    A new object is constructed on every call so callers can never share
    mutable state with each other or with this module.
    """
    nodes = [
        Node(id="ui-web", type=_NODE_UI, name="Bookmarks Web UI"),
        Node(id="svc-api", type=_NODE_API, name="Bookmarks HTTP API"),
        Node(id="svc-links", type=_NODE_SERVICE, name="Link Service"),
        Node(id="mod-slug", type=_NODE_MODULE, name="Slug Generator"),
        Node(id="db-main", type=_NODE_DATABASE, name="Bookmarks Database"),
    ]

    edges = [
        Edge(
            id="edge-ui-calls-api",
            source="ui-web",
            target="svc-api",
            type=_EDGE_CALLS,
        ),
        Edge(
            id="edge-api-depends-links",
            source="svc-api",
            target="svc-links",
            type=_EDGE_DEPENDS_ON,
        ),
        Edge(
            id="edge-links-depends-slug",
            source="svc-links",
            target="mod-slug",
            type=_EDGE_DEPENDS_ON,
        ),
        Edge(
            id="edge-links-depends-db",
            source="svc-links",
            target="db-main",
            type=_EDGE_DEPENDS_ON,
        ),
    ]

    tasks = [
        Task(
            id="task-db-schema",
            node_id="db-main",
            title="Create the bookmarks table and migration",
        ),
        Task(
            id="task-slug",
            node_id="mod-slug",
            title="Implement slug generation",
        ),
        Task(
            id="task-link-service",
            node_id="svc-links",
            title="Implement the link service",
            depends_on=["task-db-schema", "task-slug"],
        ),
        Task(
            id="task-api",
            node_id="svc-api",
            title="Expose the bookmarks HTTP endpoints",
            depends_on=["task-link-service"],
        ),
        Task(
            id="task-web-ui",
            node_id="ui-web",
            title="Build the bookmarks web UI",
            depends_on=["task-api"],
        ),
    ]

    return ArchitectureGraph(
        project_name="Bookmarks Service",
        requirement=requirement,
        nodes=nodes,
        edges=edges,
        tasks=tasks,
    )


# --- fixture refinement actions --------------------------------------------

def _apply_add_auth(graph: ArchitectureGraph) -> RefinementTurn:
    """Append an auth service, an edge from the API to it, and a root task."""
    if any(n.id == "svc-auth" for n in graph.nodes):
        raise MuseSparkOutputError(
            "fixture refine: 'svc-auth' already exists; 'add auth' is not "
            "idempotent in the fixture"
        )
    if not any(n.id == "svc-api" for n in graph.nodes):
        raise MuseSparkOutputError(
            "fixture refine: 'add auth' requires a node 'svc-api' in the graph"
        )

    graph.nodes.append(
        Node(
            id="svc-auth",
            type=_NODE_SERVICE,
            name="Auth Service",
            description="User authentication and authorization",
        )
    )
    graph.edges.append(
        Edge(
            id="edge-api-depends-auth",
            source="svc-api",
            target="svc-auth",
            type=_EDGE_DEPENDS_ON,
        )
    )
    graph.tasks.append(
        Task(
            id="task-auth",
            node_id="svc-auth",
            title="Implement authentication",
            # Root task: auth is foundational and can start immediately.
        )
    )
    return RefinementTurn(
        instruction="add auth",
        node_ids_added=["svc-auth"],
        edge_ids_added=["edge-api-depends-auth"],
        task_ids_added=["task-auth"],
    )


def _apply_remove(graph: ArchitectureGraph, entity_id: str) -> RefinementTurn:
    """Remove a node or task, cascading to any task that depends on it.

    Removing a node removes its incident edges and any task whose
    ``node_id`` is that node, then transitively removes tasks that depend on
    removed tasks (their prerequisites can no longer be satisfied).
    """
    if any(n.id == entity_id for n in graph.nodes):
        removed_edges = [
            e.id
            for e in graph.edges
            if e.source == entity_id or e.target == entity_id
        ]
        direct_tasks = [t.id for t in graph.tasks if t.node_id == entity_id]
        removed_tasks = _cascade_task_removal(graph, direct_tasks)

        graph.nodes = [n for n in graph.nodes if n.id != entity_id]
        graph.edges = [e for e in graph.edges if e.id not in removed_edges]
        graph.tasks = [t for t in graph.tasks if t.id not in removed_tasks]
        _cleanup_depends_on(graph, removed_tasks)

        return RefinementTurn(
            instruction=f"remove {entity_id}",
            node_ids_removed=[entity_id],
            edge_ids_removed=removed_edges,
            task_ids_removed=removed_tasks,
        )

    if any(t.id == entity_id for t in graph.tasks):
        removed_tasks = _cascade_task_removal(graph, [entity_id])
        graph.tasks = [t for t in graph.tasks if t.id not in removed_tasks]
        _cleanup_depends_on(graph, removed_tasks)
        return RefinementTurn(
            instruction=f"remove {entity_id}",
            task_ids_removed=removed_tasks,
        )

    raise MuseSparkOutputError(
        f"fixture refine: cannot remove unknown entity {entity_id!r}"
    )


def _apply_rename(
    graph: ArchitectureGraph, old_id: str, new_id: str
) -> RefinementTurn:
    """Rename a node or task, updating references in the graph in place.

    Rename is recorded as a remove+add pair in the ``RefinementTurn`` — the
    history log has no dedicated "modified" concept. Edges and tasks whose
    references change are updated in the graph state but are not listed in
    the history: only the renamed entity's IDs appear.
    """
    if not _ENTITY_ID_RE.match(new_id):
        raise MuseSparkOutputError(
            f"fixture refine: {new_id!r} is not a valid entity id "
            f"(must match ^[A-Za-z][A-Za-z0-9_-]{{0,63}}$)"
        )

    if old_id == new_id:
        # A rename to the same id is a no-op, recorded honestly as an empty turn.
        return RefinementTurn(instruction=f"rename {old_id} to {new_id}")

    for i, n in enumerate(graph.nodes):
        if n.id == old_id:
            if any(m.id == new_id for m in graph.nodes):
                raise MuseSparkOutputError(
                    f"fixture refine: node {new_id!r} already exists"
                )
            graph.nodes[i] = n.model_copy(update={"id": new_id})
            for j, e in enumerate(graph.edges):
                update: dict[str, str] = {}
                if e.source == old_id:
                    update["source"] = new_id
                if e.target == old_id:
                    update["target"] = new_id
                if update:
                    graph.edges[j] = e.model_copy(update=update)
            for j, t in enumerate(graph.tasks):
                if t.node_id == old_id:
                    graph.tasks[j] = t.model_copy(update={"node_id": new_id})
            return RefinementTurn(
                instruction=f"rename {old_id} to {new_id}",
                node_ids_added=[new_id],
                node_ids_removed=[old_id],
            )

    for i, t in enumerate(graph.tasks):
        if t.id == old_id:
            if any(m.id == new_id for m in graph.tasks):
                raise MuseSparkOutputError(
                    f"fixture refine: task {new_id!r} already exists"
                )
            graph.tasks[i] = t.model_copy(update={"id": new_id})
            for j, other in enumerate(graph.tasks):
                if old_id in other.depends_on:
                    new_deps = [
                        new_id if d == old_id else d for d in other.depends_on
                    ]
                    graph.tasks[j] = other.model_copy(
                        update={"depends_on": new_deps}
                    )
            return RefinementTurn(
                instruction=f"rename {old_id} to {new_id}",
                task_ids_added=[new_id],
                task_ids_removed=[old_id],
            )

    raise MuseSparkOutputError(
        f"fixture refine: cannot rename unknown entity {old_id!r}"
    )


def _cascade_task_removal(
    graph: ArchitectureGraph, initial: list[str]
) -> list[str]:
    """Return the sorted set of task ids to remove, including transitive
    dependents whose prerequisites will no longer be satisfiable."""
    removed = set(initial)
    while True:
        new = {
            t.id
            for t in graph.tasks
            if t.id not in removed and any(d in removed for d in t.depends_on)
        }
        if not new:
            return sorted(removed)
        removed |= new


def _cleanup_depends_on(graph: ArchitectureGraph, removed_ids: list[str]) -> None:
    """Drop references to removed task ids from surviving tasks' ``depends_on``."""
    removed = set(removed_ids)
    for t in graph.tasks:
        if t.depends_on:
            new_deps = [d for d in t.depends_on if d not in removed]
            if new_deps != t.depends_on:
                t.depends_on = new_deps