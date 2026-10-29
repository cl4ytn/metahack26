"""Muse Spark adapter interface and a replayed fixture implementation.

Muse Spark is the component that turns a natural-language requirement into an
`ArchitectureGraph`. The real Muse Spark service is NOT available for this
project and its request/response shapes are unknown, so this module defines
only the narrow Python-level contract plus a fixture that replays a fixed
graph.

Nothing here invents an HTTP endpoint, a JSON payload, a prompt or a model
response shape. A real adapter can implement `MuseSparkAdapter` later without
touching any other module.

The fixture is a REPLAY, not a model call. Its class name, its log output and
every place it is surfaced must say so.

Contract
--------
`MuseSparkAdapter.generate_graph(requirement) -> ArchitectureGraph` produces a
DRAFT graph. It does NOT validate graph semantics and does NOT approve
anything: callers must run `validate_graph` and obtain user approval before
persistence or execution.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from backend.app.models.graph import (
    ArchitectureGraph,
    Edge,
    EdgeType,
    Node,
    NodeType,
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
# map it to a single failure response. The fixture raises none of them.

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


# --- replayed fixture -------------------------------------------------------

class FixtureMuseSpark:
    """Replayed Muse Spark stand-in. NOT a model call.

    Returns the same fixed architecture graph on every call, with the supplied
    requirement text recorded on it. The graph is a draft: it is unapproved and
    carries no execution or verification evidence.
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