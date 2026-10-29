from __future__ import annotations

"""Architecture Graph API.

Handles CRUD operations, validation, human-in-the-loop approval,
and transitive blast radius calculations for architecture components.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.models.graph import (
    ArchitectureGraph,
    GraphStatus,
    Node,
    Task,
    utc_now,
)
from backend.app.services.muse_spark import FixtureMuseSpark
from backend.app.services.validator import validate_graph
from backend.app.storage.yaml_store import (
    GraphFileNotFoundError,
    GraphStoreError,
    load_graph,
    save_graph,
)

router = APIRouter(prefix="/api/architecture", tags=["architecture"])

YAML_PATH = Path("architecture.yaml")


# ---------------------------------------------------------------------------
# State Management
# ---------------------------------------------------------------------------

def _load_initial_graph() -> ArchitectureGraph:
    """Load existing graph from YAML or generate initial baseline demo graph."""
    if YAML_PATH.exists():
        try:
            graph = load_graph(YAML_PATH)
            if graph.approved_revision != graph.revision or any(v.graph_revision is None for v in graph.verifications):
                from backend.app.models.graph import TaskStatus
                graph = graph.model_copy(update={"status": GraphStatus.DRAFT, "approved_revision": None, "approved_at": None, "executions": [], "verifications": [], "tasks": [t.model_copy(update={"status": TaskStatus.PENDING, "execution_ids": [], "verification_ids": []}) for t in graph.tasks]})
            return graph
        except Exception:
            pass

    return FixtureMuseSpark().generate_graph(
        "Scale Bookmarks Service with LRU cache, rate limiting on Slug Generator, and Postgres read replica..."
    )


# Active in-memory graph state
_active_graph: ArchitectureGraph = _load_initial_graph()


def get_current_graph() -> ArchitectureGraph:
    """Return the active in-memory architecture graph."""
    global _active_graph
    return _active_graph


def set_current_graph(graph: ArchitectureGraph) -> None:
    """Update the active in-memory architecture graph."""
    global _active_graph
    try:
        save_graph(graph, YAML_PATH)
    except (GraphStoreError, OSError) as err:
        raise HTTPException(status_code=400, detail=f"Graph not saved: {err}") from err
    _active_graph = graph


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

def save_edited_graph(graph: ArchitectureGraph) -> ArchitectureGraph:
    current = get_current_graph()
    def semantic(g):
        data = g.model_dump(mode="json")
        return {k: data[k] for k in ("project_name", "requirement", "nodes", "edges")} | {"tasks": [{k: v for k, v in t.items() if k not in ("status", "execution_ids", "verification_ids")} for t in data["tasks"]]}
    if semantic(graph) == semantic(current):
        return current
    from backend.app.models.graph import TaskStatus
    edited = graph.model_copy(update={"revision": current.revision + 1, "status": GraphStatus.DRAFT, "approved_at": None, "approved_revision": None, "executions": [], "verifications": [], "tasks": [t.model_copy(update={"status": TaskStatus.PENDING, "execution_ids": [], "verification_ids": []}) for t in graph.tasks]})
    set_current_graph(edited)
    return edited


class ValidationResponse(BaseModel):
    """Result of topological and integrity validation on the DAG."""
    is_valid: bool = Field(..., description="True if graph has 0 cycles and valid references")
    issues: list[dict[str, Any]] = Field(default_factory=list, description="List of identified issues")


class RevisionImpactRequest(BaseModel):
    """Request payload to calculate blast radius when revising a node or task."""
    target_type: str = Field(..., description="'node' or 'task'")
    target_id: str = Field(..., description="Identifier of the node or task being revised")


class RevisionImpactResponse(BaseModel):
    """Calculated blast radius across downstream nodes and tasks."""
    target_id: str
    target_type: str
    impacted_node_ids: list[str]
    impacted_task_ids: list[str]
    blast_radius_percentage: float
    description: str


# ---------------------------------------------------------------------------
# Blast Radius Calculation Helper
# ---------------------------------------------------------------------------

def calculate_blast_radius(
    graph: ArchitectureGraph, target_type: str, target_id: str
) -> tuple[set[str], set[str]]:
    """Traverse downstream DAG dependencies to calculate affected entities.

    In the edge convention:
      - edge.source calls or depends on edge.target.
      - Therefore, if edge.target is revised, edge.source is impacted!
    In task dependencies:
      - task.depends_on contains prerequisites.
      - If a prerequisite task changes, any task depending on it is impacted.
    """
    impacted_nodes: set[str] = set()
    impacted_tasks: set[str] = set()

    if target_type == "node":
        impacted_nodes.add(target_id)

        # Transitive propagation along incoming edges
        expanded = True
        while expanded:
            expanded = False
            for edge in graph.edges:
                if edge.target in impacted_nodes and edge.source not in impacted_nodes:
                    impacted_nodes.add(edge.source)
                    expanded = True

        # Identify all tasks attached to impacted nodes
        for task in graph.tasks:
            if task.node_id in impacted_nodes:
                impacted_tasks.add(task.id)

    elif target_type == "task":
        impacted_tasks.add(target_id)

    # Transitive propagation along task dependencies
    expanded = True
    while expanded:
        expanded = False
        for task in graph.tasks:
            if task.id not in impacted_tasks:
                if any(dep in impacted_tasks for dep in task.depends_on):
                    impacted_tasks.add(task.id)
                    expanded = True

    # Associate nodes of any indirectly impacted tasks
    for task in graph.tasks:
        if task.id in impacted_tasks:
            impacted_nodes.add(task.node_id)

    return impacted_nodes, impacted_tasks


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=ArchitectureGraph)
def get_graph() -> ArchitectureGraph:
    """Retrieve the current architecture graph specification."""
    return get_current_graph()


@router.put("", response_model=ArchitectureGraph)
def update_graph(graph: ArchitectureGraph) -> ArchitectureGraph:
    """Update the entire architecture graph specification."""
    return save_edited_graph(graph)


@router.post("/node", response_model=Node)
def add_node(node: Node) -> Node:
    """Add a new architectural component node to the graph."""
    graph = get_current_graph()
    if any(n.id == node.id for n in graph.nodes):
        raise HTTPException(status_code=400, detail=f"Node '{node.id}' already exists")

    updated = graph.model_copy(update={"nodes": [*graph.nodes, node]})
    save_edited_graph(updated)
    return node


@router.post("/task", response_model=Task)
def add_task(task: Task) -> Task:
    """Add a new execution task tied to a specific node."""
    graph = get_current_graph()
    if any(t.id == task.id for t in graph.tasks):
        raise HTTPException(status_code=400, detail=f"Task '{task.id}' already exists")
    if not any(n.id == task.node_id for n in graph.nodes):
        raise HTTPException(status_code=400, detail=f"Target node '{task.node_id}' does not exist")

    updated = graph.model_copy(update={"tasks": [*graph.tasks, task]})
    save_edited_graph(updated)
    return task


@router.post("/validate", response_model=ValidationResponse)
def validate_current_graph() -> ValidationResponse:
    """Validate graph topology, ensuring zero cycles and valid file/node references."""
    graph = get_current_graph()
    report = validate_graph(graph)
    return ValidationResponse(
        is_valid=report.is_valid,
        issues=[
            {
                "code": err.code,
                "message": err.message,
                "entity_type": err.entity_type,
                "entity_id": err.entity_id,
                "field": err.field,
            }
            for err in report.errors
        ],
    )


class ApprovalRequest(BaseModel):
    revision: int


@router.post("/approve", response_model=ArchitectureGraph)
def approve_graph(payload: ApprovalRequest | None = None) -> ArchitectureGraph:
    """Human-in-the-loop approval gate.

    Verifies DAG validity, sets status to APPROVED with timestamp,
    and atomically saves to architecture.yaml.
    """
    graph = get_current_graph()
    if payload is not None and payload.revision != graph.revision:
        raise HTTPException(409, "Graph revision changed; reload and review before approval.")
    report = validate_graph(graph)
    if not report.is_valid:
        error_messages = [e.message for e in report.errors]
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve invalid graph: {error_messages}",
        )

    approved_graph = graph.model_copy(
        update={"status": GraphStatus.APPROVED, "approved_at": utc_now(), "approved_revision": graph.revision}
    )
    from backend.app.services.scheduler import reconcile_schedule
    approved_graph = reconcile_schedule(approved_graph)
    set_current_graph(approved_graph)

    return approved_graph


@router.post("/impact", response_model=RevisionImpactResponse)
def compute_revision_impact(payload: RevisionImpactRequest) -> RevisionImpactResponse:
    """Calculate the downstream blast radius when revising a node or task."""
    graph = get_current_graph()
    impacted_nodes, impacted_tasks = calculate_blast_radius(
        graph, payload.target_type, payload.target_id
    )

    total_entities = max(len(graph.nodes) + len(graph.tasks), 1)
    impacted_count = len(impacted_nodes) + len(impacted_tasks)
    percentage = round((impacted_count / total_entities) * 100, 1)

    description = (
        f"Revising {payload.target_type} '{payload.target_id}' impacts {len(impacted_nodes)} "
        f"node(s) and {len(impacted_tasks)} task(s) across the dependency DAG."
    )

    return RevisionImpactResponse(
        target_id=payload.target_id,
        target_type=payload.target_type,
        impacted_node_ids=sorted(list(impacted_nodes)),
        impacted_task_ids=sorted(list(impacted_tasks)),
        blast_radius_percentage=percentage,
        description=description,
    )


@router.post("/reset", response_model=ArchitectureGraph)
def reset_graph() -> ArchitectureGraph:
    """Reset the graph to the baseline demo state."""
    fresh = FixtureMuseSpark().generate_graph(
        "Scale Bookmarks Service with LRU cache, rate limiting on Slug Generator, and Postgres read replica..."
    )
    fresh = fresh.model_copy(update={"revision": get_current_graph().revision + 1})
    set_current_graph(fresh)
    return fresh


@router.post("/save")
def persist_yaml() -> dict[str, str]:
    """Atomically write the in-memory graph to architecture.yaml."""
    graph = get_current_graph()
    try:
        save_graph(graph, YAML_PATH)
        return {"status": "saved", "path": str(YAML_PATH.resolve())}
    except GraphStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/load")
def load_yaml() -> ArchitectureGraph:
    """Reload graph state from architecture.yaml on disk."""
    try:
        graph = load_graph(YAML_PATH)
        set_current_graph(graph)
        return graph
    except GraphFileNotFoundError:
        raise HTTPException(status_code=404, detail="architecture.yaml not found")
    except GraphStoreError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
