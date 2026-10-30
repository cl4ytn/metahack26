"""Task lifecycle API.

Endpoints:
  GET  /api/tasks                    - list tasks + schedule classification
  POST /api/tasks/schedule           - apply scheduler transitions (pending -> ready, * -> blocked)
  POST /api/tasks/{task_id}/execute  - run one ready task through the pipeline

Backed by the real scheduler and the real test runner. Persists via save_graph
only when the graph is valid. The coding agent is injected (fixture by default);
fixture labelling is visible in responses.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.models.graph import (
    ArchitectureGraph,
    ExecutionResult,
    GraphStatus,
    Task,
    TaskStatus,
    VerificationResult,
)
from backend.app.services.coding_agent import (
    AgentResult,
    CodingAgentAdapter,
    FixtureCodingAgent,
    TaskContext,
)
from backend.app.services.scheduler import (
    GraphNotApprovedError,
    SchedulePlan,
    UnschedulableGraphError,
    build_schedule,
)
from backend.app.services.test_runner import run_verification
from backend.app.services.validator import validate_graph
from backend.app.storage.yaml_store import (
    GraphStoreError,
    InvalidGraphError,
    load_graph,
    save_graph,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# Dependency seams (overridden in tests; swapped later for real adapters)
# ---------------------------------------------------------------------------

def get_architecture_path() -> Path:
    return Path(__file__).resolve().parents[2] / "architecture.yaml"


def get_coding_agent() -> CodingAgentAdapter:
    return FixtureCodingAgent()


def default_verification_command(task_id: str) -> list[str]:
    """Demo command for the fixture agent.

    The fixture does not produce runnable code yet; this runs a real
    subprocess through the real test_runner (exit 0 -> passed). Replace with
    a task-specific pytest target once code generation is real.
    """
    return [
        sys.executable,
        "-c",
        f"print('graphpilot demo verification for {task_id}')",
    ]


def get_verification_command_builder() -> Callable[[str], list[str]]:
    return default_verification_command


# ---------------------------------------------------------------------------
# Local response models (graph.py stays the canonical graph contract)
# ---------------------------------------------------------------------------

class TaskSummary(BaseModel):
    id: str
    node_id: str
    title: str
    status: TaskStatus
    depends_on: list[str]
    execution_ids: list[str]
    verification_ids: list[str]
    schedule: Literal["ready", "blocked", "waiting"] | None = None
    schedule_reason: str | None = None


class TasksListResponse(BaseModel):
    project_name: str
    graph_status: GraphStatus
    schedulable: bool
    schedule_error: str | None = None
    tasks: list[TaskSummary]


class TransitionRecord(BaseModel):
    task_id: str
    from_status: str
    to_status: str


class ScheduleApplyResponse(BaseModel):
    project_name: str
    graph_status: GraphStatus
    transitioned: list[TransitionRecord]
    ready: list[str]
    blocked: list[str]
    waiting: list[str]
    tasks: list[TaskSummary]
    saved: bool
    saved_path: str


class AdapterMetadata(BaseModel):
    name: str
    is_fixture: bool


class ExecutionPayload(BaseModel):
    id: str
    task_id: str
    agent_name: str
    external_run_id: str | None
    changed_files: list[str]
    agent_reported_success: bool | None
    timed_out: bool
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class VerificationPayload(BaseModel):
    id: str
    task_id: str
    execution_id: str
    command: str
    outcome: str
    exit_code: int | None
    passed: bool
    stdout: str
    stderr: str
    started_at: datetime
    finished_at: datetime | None


class TaskExecutionResponse(BaseModel):
    task_id: str
    final_status: TaskStatus
    execution: ExecutionPayload
    verification: VerificationPayload
    agent: AdapterMetadata
    command: list[str]
    saved: bool
    saved_path: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_or_404(path: Path) -> ArchitectureGraph:
    try:
        return load_graph(path)
    except GraphStoreError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"architecture not available: {exc}",
        ) from exc


def _find_task(graph: ArchitectureGraph, task_id: str) -> Task:
    for task in graph.tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail=f"task not found: {task_id}")


def _enum_value(x: Any) -> str:
    return x.value if hasattr(x, "value") else str(x)


def _classify(plan: SchedulePlan) -> dict[str, tuple[str, str | None]]:
    out: dict[str, tuple[str, str | None]] = {}
    for tid in plan.ready:
        out[tid] = ("ready", "all dependencies verified")
    for tid in plan.blocked:
        out[tid] = ("blocked", "a dependency is failed or blocked")
    for tid in plan.waiting:
        out[tid] = ("waiting", "dependencies not yet verified")
    return out


def _summarise_tasks(
    graph: ArchitectureGraph, plan: SchedulePlan | None
) -> list[TaskSummary]:
    classifications = _classify(plan) if plan is not None else {}
    summaries: list[TaskSummary] = []
    for t in graph.tasks:
        cls, reason = classifications.get(t.id, (None, None))
        summaries.append(
            TaskSummary(
                id=t.id,
                node_id=t.node_id,
                title=t.title,
                status=t.status,
                depends_on=list(t.depends_on),
                execution_ids=list(t.execution_ids),
                verification_ids=list(t.verification_ids),
                schedule=cls,
                schedule_reason=reason,
            )
        )
    return summaries


def _build_context(graph: ArchitectureGraph, task_id: str, workdir: Path) -> TaskContext:
    """Deep-copy the graph so the agent sees a read-only snapshot."""
    graph_copy = graph.model_copy(deep=True)
    task_copy = next(t for t in graph_copy.tasks if t.id == task_id)
    return TaskContext(task=task_copy, graph=graph_copy, workdir=workdir)


def _persist(graph: ArchitectureGraph, path: Path) -> str:
    """Validate + save. Raises HTTPException(409) on invalid graph."""
    try:
        save_graph(graph, path)
    except InvalidGraphError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "graph invalid; refusing to persist",
                "messages": exc.report.messages(),
            },
        ) from exc
    return str(path)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=TasksListResponse)
def list_tasks(
    path: Path = Depends(get_architecture_path),
) -> TasksListResponse:
    graph = _load_or_404(path)
    schedulable = True
    schedule_error: str | None = None
    plan: SchedulePlan | None = None
    try:
        plan = build_schedule(graph)
    except UnschedulableGraphError as exc:
        schedulable = False
        schedule_error = f"invalid graph ({len(exc.report.errors)} issue(s))"
    except GraphNotApprovedError as exc:
        schedulable = False
        schedule_error = (
            f"graph not approved (status={_enum_value(exc.status)})"
        )

    return TasksListResponse(
        project_name=graph.project_name,
        graph_status=graph.status,
        schedulable=schedulable,
        schedule_error=schedule_error,
        tasks=_summarise_tasks(graph, plan),
    )


@router.post("/schedule", response_model=ScheduleApplyResponse)
def apply_schedule(
    path: Path = Depends(get_architecture_path),
) -> ScheduleApplyResponse:
    graph = _load_or_404(path)
    try:
        plan = build_schedule(graph)
    except UnschedulableGraphError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "graph invalid", "messages": exc.report.messages()},
        ) from exc
    except GraphNotApprovedError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"graph not approved (status={_enum_value(exc.status)})",
        ) from exc

    by_id = {t.id: t for t in graph.tasks}
    transitions: list[TransitionRecord] = []

    for tid in plan.ready:
        task = by_id[tid]
        if task.status == TaskStatus.PENDING:
            transitions.append(
                TransitionRecord(
                    task_id=tid, from_status="pending", to_status="ready"
                )
            )
            task.status = TaskStatus.READY

    for tid in plan.blocked:
        task = by_id[tid]
        if task.status in (TaskStatus.PENDING, TaskStatus.READY):
            transitions.append(
                TransitionRecord(
                    task_id=tid,
                    from_status=_enum_value(task.status),
                    to_status="blocked",
                )
            )
            task.status = TaskStatus.BLOCKED

    saved_path = _persist(graph, path)

    return ScheduleApplyResponse(
        project_name=graph.project_name,
        graph_status=graph.status,
        transitioned=transitions,
        ready=list(plan.ready),
        blocked=list(plan.blocked),
        waiting=list(plan.waiting),
        tasks=_summarise_tasks(graph, plan),
        saved=True,
        saved_path=saved_path,
    )


@router.post("/{task_id}/execute", response_model=TaskExecutionResponse)
def execute_task(
    task_id: str,
    path: Path = Depends(get_architecture_path),
    agent: CodingAgentAdapter = Depends(get_coding_agent),
    command_builder: Callable[[str], list[str]] = Depends(
        get_verification_command_builder
    ),
) -> TaskExecutionResponse:
    graph = _load_or_404(path)

    report = validate_graph(graph)
    if not report.is_valid:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "cannot execute on invalid graph",
                "messages": report.messages(),
            },
        )

    task = _find_task(graph, task_id)
    if task.status != TaskStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=(
                f"task {task_id} is '{_enum_value(task.status)}', "
                f"expected 'ready'"
            ),
        )

    workdir = path.parent  # cwd convention: directory of architecture.yaml
    task.status = TaskStatus.RUNNING
    execution_id = f"exec-{uuid.uuid4().hex}"
    started_at = datetime.now(timezone.utc)
    context = _build_context(graph, task_id, workdir)

    # 1. Agent (may raise; a claimed result is not evidence).
    try:
        agent_result: AgentResult = agent.execute_task(context)
    except Exception as exc:  # adapter bug or unexpected failure
        finished_at = datetime.now(timezone.utc)
        failure_exec = ExecutionResult(
            id=execution_id,
            task_id=task_id,
            agent_name=agent.name(),
            external_run_id=None,
            started_at=started_at,
            finished_at=finished_at,
            changed_files=[],
            diff="",
            agent_reported_success=False,
            timed_out=False,
            error=f"{type(exc).__name__}: {exc}",
        )
        graph.executions.append(failure_exec)
        task.execution_ids.append(execution_id)
        task.status = TaskStatus.FAILED
        saved_path = _persist(graph, path)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "coding agent failed",
                "task_id": task_id,
                "execution_id": execution_id,
                "error_message": failure_exec.error,
                "saved_path": saved_path,
            },
        ) from exc

    # 2. Record the CLAIMED result. Never grounds for verified.
    finished_at = datetime.now(timezone.utc)
    execution = ExecutionResult(
        id=execution_id,
        task_id=task_id,
        agent_name=agent_result.agent_name,
        external_run_id=agent_result.external_run_id,
        started_at=started_at,
        finished_at=finished_at,
        changed_files=list(agent_result.changed_files),
        diff=agent_result.diff,
        agent_reported_success=agent_result.agent_reported_success,
        timed_out=False,
        error=None,
    )
    graph.executions.append(execution)
    task.execution_ids.append(execution_id)

    # 3. Lifecycle: implemented -> verifying. (The claim does not skip ahead.)
    task.status = TaskStatus.IMPLEMENTED
    task.status = TaskStatus.VERIFYING

    # 4. REAL verification: real subprocess, real exit code.
    command = command_builder(task_id)
    verification_id = f"ver-{uuid.uuid4().hex}"
    verification: VerificationResult = run_verification(
        command,
        verification_id=verification_id,
        task_id=task_id,
        execution_id=execution_id,
        cwd=workdir,
    )
    graph.verifications.append(verification)
    task.verification_ids.append(verification_id)

    # 5. Final state from the REAL outcome, never from the agent's claim.
    task.status = (
        TaskStatus.VERIFIED if verification.passed else TaskStatus.FAILED
    )

    saved_path = _persist(graph, path)

    return TaskExecutionResponse(
        task_id=task_id,
        final_status=task.status,
        execution=ExecutionPayload(
            id=execution.id,
            task_id=execution.task_id,
            agent_name=execution.agent_name,
            external_run_id=execution.external_run_id,
            changed_files=list(execution.changed_files),
            agent_reported_success=execution.agent_reported_success,
            timed_out=execution.timed_out,
            error=execution.error,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
        ),
        verification=VerificationPayload(
            id=verification.id,
            task_id=verification.task_id,
            execution_id=verification.execution_id,
            command=verification.command,
            outcome=_enum_value(verification.outcome),
            exit_code=verification.exit_code,
            passed=verification.passed,
            stdout=verification.stdout,
            stderr=verification.stderr,
            started_at=verification.started_at,
            finished_at=verification.finished_at,
        ),
        agent=AdapterMetadata(name=agent.name(), is_fixture=agent.is_fixture()),
        command=list(command),
        saved=True,
        saved_path=saved_path,
    )