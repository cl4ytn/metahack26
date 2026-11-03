"""Canonical GraphPilot data contract.

This module defines the single schema shared by the model adapter, validator,
YAML store, scheduler, API and frontend.

It deliberately enforces only *local* constraints (types, enums, ID format,
non-empty strings, per-record consistency). Cross-record integrity (duplicate
IDs, unresolved references, dependency cycles) belongs to
``services/validator.py`` so that an invalid graph can still be loaded and
reported on with actionable errors instead of failing with a generic
parsing error.

Conventions
-----------
* Edge direction: ``source`` depends on / uses ``target``.
* Task dependency: ``task.depends_on`` lists tasks that must be VERIFIED
  before this task may run.
* Datetimes are timezone-aware UTC. Use ``model_dump(mode="json")`` when
  serialising so they become ISO-8601 strings that YAML can store safely.
* ``refinement_history`` is an append-only audit log of refine turns, not a
  set of live references. The validator deliberately does NOT chase IDs in
  it: a node removed in turn 2 is allowed to appear in turn 1's
  ``node_ids_added``, and a renamed ID appears once as removed and once as
  added (rename is expressed as a remove+add pair, not a dedicated field).

Schema version
--------------
``SCHEMA_VERSION = "1.1"`` adds ``refinement_history``. Files with
``schema_version == "1.0"`` still load, still parse, and remain 1.0 on save:
the version is never silently bumped. Refinement itself (the adapter's
``refine_graph`` and ``POST /api/architecture/refine``) requires 1.1; a 1.0
graph must be regenerated first.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

SCHEMA_VERSION = "1.1"

# ---------------------------------------------------------------------------
# Shared field types
# ---------------------------------------------------------------------------

# Stable, human-readable identifier, e.g. "auth_service", "task-001".
EntityId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
    ),
]

# Non-empty single-line-ish text such as names and titles.
ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class GraphPilotModel(BaseModel):
    """Base class: reject unknown fields so schema drift is caught on load."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    SERVICE = "service"
    MODULE = "module"
    API = "api"
    DATABASE = "database"
    UI = "ui"
    EXTERNAL = "external"


class EdgeType(str, Enum):
    """Relationship kinds. In every case, source depends on target."""

    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"


class TaskStatus(str, Enum):
    """Task lifecycle: pending -> ready -> running -> implemented ->
    verifying -> verified, plus blocked and failed.

    * implemented: an attempt produced inspectable code changes.
    * verified:    required independent tests passed and evidence recorded.
    * blocked:     prerequisites unsatisfied.
    * failed:      the relevant operation failed.
    """

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    IMPLEMENTED = "implemented"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    BLOCKED = "blocked"
    FAILED = "failed"


class GraphStatus(str, Enum):
    DRAFT = "draft"  # proposed or edited; not yet approved by the user
    APPROVED = "approved"  # validated and approved; execution may begin


class VerificationOutcome(str, Enum):
    PASSED = "passed"  # test command ran and exited 0
    FAILED = "failed"  # test command ran and reported failures
    TIMED_OUT = "timed_out"  # test command exceeded its time limit
    INFRASTRUCTURE_ERROR = "infrastructure_error"  # could not run the tests


# ---------------------------------------------------------------------------
# Architecture entities
# ---------------------------------------------------------------------------


class Node(GraphPilotModel):
    """An architectural element (service, module, API, database, ...)."""

    id: EntityId
    name: ShortText
    type: NodeType
    description: str = ""
    # Repository-relative paths this node is expected to own. Used by the
    # context builder to select relevant source files.
    files: list[str] = Field(default_factory=list)


class Edge(GraphPilotModel):
    """A directed relationship: ``source`` depends on ``target``."""

    id: EntityId
    source: EntityId
    target: EntityId
    type: EdgeType = EdgeType.DEPENDS_ON
    description: str = ""


# ---------------------------------------------------------------------------
# Execution and verification evidence
# ---------------------------------------------------------------------------


class ExecutionResult(GraphPilotModel):
    """Evidence from one coding-agent attempt.

    This records what the agent did. It is NOT verification:
    ``agent_reported_success`` is the agent's own unverified claim and must
    never be used to mark a task verified.
    """

    id: EntityId
    task_id: EntityId
    agent_name: str = ""
    external_run_id: str | None = None  # identifier from the agent, if any
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    changed_files: list[str] = Field(default_factory=list)
    diff: str = ""
    agent_reported_success: bool | None = None  # unverified claim
    timed_out: bool = False
    error: str | None = None


class VerificationResult(GraphPilotModel):
    """Evidence from one independent test run, tied to a task and execution."""

    id: EntityId
    task_id: EntityId
    execution_id: EntityId
    command: str = Field(min_length=1)
    outcome: VerificationOutcome
    exit_code: int | None = None  # None when no process result is available
    stdout: str = ""
    stderr: str = ""
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    @property
    def passed(self) -> bool:
        return self.outcome == VerificationOutcome.PASSED

    @model_validator(mode="after")
    def _passed_requires_zero_exit(self) -> "VerificationResult":
        if self.outcome == VerificationOutcome.PASSED and self.exit_code != 0:
            raise ValueError("outcome 'passed' requires exit_code == 0")
        return self


# ---------------------------------------------------------------------------
# Implementation tasks
# ---------------------------------------------------------------------------


class Task(GraphPilotModel):
    """A unit of implementation work for one architecture node."""

    id: EntityId
    title: ShortText
    description: str = ""
    node_id: EntityId  # the node this task implements
    depends_on: list[EntityId] = Field(default_factory=list)  # prerequisite tasks
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    # References into ArchitectureGraph.executions / .verifications.
    execution_ids: list[EntityId] = Field(default_factory=list)
    verification_ids: list[EntityId] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Refinement history
# ---------------------------------------------------------------------------


class RefinementTurn(GraphPilotModel):
    """One refine step, logged in ``ArchitectureGraph.refinement_history``.

    This is an audit trail, not a live reference set. A node that was removed
    in turn 2 may legitimately appear in ``node_ids_added`` of turn 1; the
    validator does not chase these IDs. Turn order is list order — no
    timestamp, no snapshot. A rename is expressed as one removal and one
    addition within the same turn.
    """

    instruction: str
    node_ids_added: list[EntityId] = Field(default_factory=list)
    node_ids_removed: list[EntityId] = Field(default_factory=list)
    edge_ids_added: list[EntityId] = Field(default_factory=list)
    edge_ids_removed: list[EntityId] = Field(default_factory=list)
    task_ids_added: list[EntityId] = Field(default_factory=list)
    task_ids_removed: list[EntityId] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level graph
# ---------------------------------------------------------------------------


class ArchitectureGraph(GraphPilotModel):
    """The complete persisted state of a GraphPilot project."""

    schema_version: Literal["1.0", "1.1"] = SCHEMA_VERSION  # type: ignore[assignment]
    project_name: ShortText
    requirement: str = ""  # the originating natural-language requirement
    status: GraphStatus = GraphStatus.DRAFT
    approved_at: datetime | None = None
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    executions: list[ExecutionResult] = Field(default_factory=list)
    verifications: list[VerificationResult] = Field(default_factory=list)
    refinement_history: list[RefinementTurn] = Field(default_factory=list)