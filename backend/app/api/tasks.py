from __future__ import annotations

"""Local command verification. This API is intended for trusted local use."""
from pathlib import Path
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.app.api.architecture import get_current_graph, set_current_graph
from backend.app.models.graph import ExecutionResult, GraphStatus, TaskStatus, utc_now
from backend.app.services.scheduler import build_schedule, reconcile_schedule
from backend.app.services.test_runner import run_verification

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

class StatusUpdateRequest(BaseModel):
    status: TaskStatus

class VerifyTaskRequest(BaseModel):
    command: list[str] | None = None
    project_path: str = "."
    agent_name: str = "User supplied attempt"
    diff: str = ""
    changed_files: list[str] = Field(default_factory=list)
    simulate_failure: bool = False


def calculate_downstream_blocked(tasks, failed_task_id):
    ids = {failed_task_id}
    while True:
        expanded = ids | {t.id for t in tasks if any(d in ids for d in t.depends_on)}
        if expanded == ids:
            return sorted(ids - {failed_task_id})
        ids = expanded


@router.get("/schedule")
def get_task_schedule():
    graph = get_current_graph()
    if graph.status != GraphStatus.APPROVED:
        return {"ready": [], "blocked": [], "waiting": [t.id for t in graph.tasks], "is_approved": False}
    plan = build_schedule(graph)
    return {"ready": plan.ready, "blocked": plan.blocked, "waiting": plan.waiting, "is_approved": True}


@router.post("/{task_id}/status")
def update_task_status(task_id: str, payload: StatusUpdateRequest):
    raise HTTPException(400, "Direct status overrides are disabled. Use verification or reset; VERIFIED requires recorded command evidence.")


@router.post("/{task_id}/verify")
def verify_task(task_id: str, payload: VerifyTaskRequest) -> dict[str, Any]:
    graph = get_current_graph()
    task = next((t for t in graph.tasks if t.id == task_id), None)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    if graph.status != GraphStatus.APPROVED or graph.approved_revision != graph.revision:
        raise HTTPException(409, "Approve this exact graph revision before verification.")
    if task.status == TaskStatus.VERIFIED or not all(next(t for t in graph.tasks if t.id == d).status == TaskStatus.VERIFIED for d in task.depends_on):
        raise HTTPException(409, "Task is not ready: reset verified tasks or verify every prerequisite first.")
    if payload.simulate_failure:
        raise HTTPException(400, "Simulation is not verification. Run an actual test command; no simulated evidence is accepted.")
    if not payload.command or not all(part.strip() for part in payload.command):
        raise HTTPException(400, "Configure a real test command as an argv list, such as [python, -m, pytest, path/to/test.py]. No default test is fabricated.")
    project = Path(payload.project_path).resolve()
    if not project.is_dir():
        raise HTTPException(400, "project_path must be an existing project directory.")
    execution = ExecutionResult(id=f"exec-{uuid4().hex[:8]}", task_id=task_id, agent_name=payload.agent_name, changed_files=payload.changed_files, diff=payload.diff, finished_at=utc_now())
    result = run_verification(command=payload.command, verification_id=f"verif-{uuid4().hex[:8]}", task_id=task_id, execution_id=execution.id, cwd=project, timeout_seconds=30)
    result = result.model_copy(update={"graph_revision": graph.revision, "project_path": str(project), "is_simulation": False})
    # Another request may have edited/replaced the graph while the subprocess ran.
    current = get_current_graph()
    if current is not graph:
        raise HTTPException(409, "Graph changed during verification; result was not applied. Retry against the current approved revision.")
    status = TaskStatus.VERIFIED if result.passed else TaskStatus.FAILED
    impacted = calculate_downstream_blocked(graph.tasks, task_id)
    tasks = []
    for t in graph.tasks:
        if t.id == task_id:
            t = t.model_copy(update={"status": status, "execution_ids": [*t.execution_ids, execution.id], "verification_ids": [*t.verification_ids, result.id]})
        elif t.id in impacted:
            t = t.model_copy(update={"status": TaskStatus.PENDING})
        tasks.append(t)
    updated = reconcile_schedule(graph.model_copy(update={"tasks": tasks, "executions": [*graph.executions, execution], "verifications": [*graph.verifications, result]}))
    set_current_graph(updated)
    return {"task_id": task_id, "outcome": result.outcome.value, "exit_code": result.exit_code, "passed": result.passed, "stdout": result.stdout, "stderr": result.stderr, "new_status": status.value, "impacted_blocked_tasks": [t.id for t in updated.tasks if t.status == TaskStatus.BLOCKED], "execution": execution.model_dump(mode="json"), "verification": result.model_dump(mode="json"), "graph": updated.model_dump(mode="json"), "coverage_note": "Exit code reports only this command; acceptance-criteria coverage must be reviewed by the user."}


@router.post("/{task_id}/reset")
def reset_task(task_id: str):
    graph = get_current_graph()
    if not any(t.id == task_id for t in graph.tasks):
        raise HTTPException(404, f"Task '{task_id}' not found")
    invalidated = {task_id, *calculate_downstream_blocked(graph.tasks, task_id)}
    updated = reconcile_schedule(graph.model_copy(update={"tasks": [t.model_copy(update={"status": TaskStatus.PENDING}) if t.id in invalidated else t for t in graph.tasks]}))
    set_current_graph(updated)
    status = next(t.status for t in updated.tasks if t.id == task_id)
    return {"status": "ok", "task_id": task_id, "new_status": status.value, "graph": updated.model_dump(mode="json")}
