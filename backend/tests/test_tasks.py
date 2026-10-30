"""Tests for /api/tasks endpoints.

Covers:
  - GET  /api/tasks  (draft vs approved classification)
  - POST /api/tasks/schedule (transitions + persistence; 409 for draft)
  - POST /api/tasks/{task_id}/execute (unknown, wrong status, happy path,
    failed verification, agent exception, fixture labelling)

Uses FastAPI dependency_overrides; the schedule and test-runner contracts are
exercised as-is, no message wording from other modules is encoded here.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.tasks import (
    get_architecture_path,
    get_coding_agent,
    get_verification_command_builder,
    router,
)
from backend.app.models.graph import (
    ArchitectureGraph,
    Edge,
    EdgeType,
    GraphStatus,
    Node,
    NodeType,
    Task,
    TaskStatus,
)
from backend.app.services.coding_agent import AgentResult, FixtureCodingAgent
from backend.app.storage.yaml_store import load_graph, save_graph


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def graph_path(tmp_path: Path) -> Path:
    return tmp_path / "architecture.yaml"


def _make_graph(
    status: GraphStatus = GraphStatus.APPROVED,
    tasks: list[Task] | None = None,
) -> ArchitectureGraph:
    return ArchitectureGraph(
        project_name="test-project",
        status=status,
        approved_at=(
            datetime.now(timezone.utc)
            if status == GraphStatus.APPROVED
            else None
        ),
        nodes=[
            Node(id="svc-a", type=NodeType.SERVICE, name="Service A"),
            Node(id="svc-b", type=NodeType.SERVICE, name="Service B"),
        ],
        edges=[
            Edge(id="e-b-a", source="svc-b", target="svc-a", type=EdgeType.DEPENDS_ON),
        ],
        tasks=(
            tasks
            if tasks is not None
            else [
                Task(id="task-a", node_id="svc-a", title="Build A"),
                Task(
                    id="task-b",
                    node_id="svc-b",
                    title="Build B",
                    depends_on=["task-a"],
                ),
            ]
        ),
    )


def _wire(client: TestClient, path: Path, graph: ArchitectureGraph) -> None:
    save_graph(graph, path)
    client.app.dependency_overrides[get_architecture_path] = lambda: path


class _FakeAgent:
    """Non-fixture agent used to prove the pipeline is adapter-agnostic."""

    def __init__(
        self,
        reported_success: bool = True,
        raises: Exception | None = None,
    ) -> None:
        self._reported_success = reported_success
        self._raises = raises

    def name(self) -> str:
        return "fake-agent-test"

    def is_fixture(self) -> bool:
        return False

    def execute_task(self, context) -> AgentResult:
        if self._raises is not None:
            raise self._raises
        return AgentResult(
            agent_name=self.name(),
            changed_files=["src/demo.py"],
            diff="+ pass\n",
            agent_reported_success=self._reported_success,
        )


def _pass_cmd(task_id: str) -> list[str]:
    return [sys.executable, "-c", "print('ok')"]


def _fail_cmd(task_id: str) -> list[str]:
    return [sys.executable, "-c", "import sys; sys.exit(1)"]


# ---------------------------------------------------------------------------
# GET /api/tasks
# ---------------------------------------------------------------------------

def test_list_tasks_draft_graph_still_lists_tasks(client, graph_path):
    _wire(client, graph_path, _make_graph(status=GraphStatus.DRAFT))
    response = client.get("/api/tasks")
    assert response.status_code == 200
    body = response.json()
    assert body["schedulable"] is False
    assert body["schedule_error"] is not None
    assert [t["id"] for t in body["tasks"]] == ["task-a", "task-b"]
    assert all(t["schedule"] is None for t in body["tasks"])


def test_list_tasks_approved_graph_classifies_ready_and_waiting(client, graph_path):
    _wire(client, graph_path, _make_graph(status=GraphStatus.APPROVED))
    response = client.get("/api/tasks")
    assert response.status_code == 200
    body = response.json()
    assert body["schedulable"] is True
    by_id = {t["id"]: t for t in body["tasks"]}
    assert by_id["task-a"]["schedule"] == "ready"
    assert by_id["task-b"]["schedule"] == "waiting"


# ---------------------------------------------------------------------------
# POST /api/tasks/schedule
# ---------------------------------------------------------------------------

def test_apply_schedule_moves_pending_to_ready_and_persists(client, graph_path):
    _wire(client, graph_path, _make_graph(status=GraphStatus.APPROVED))
    response = client.post("/api/tasks/schedule")
    assert response.status_code == 200
    body = response.json()
    assert any(
        t["task_id"] == "task-a" and t["to_status"] == "ready"
        for t in body["transitioned"]
    )
    assert body["saved"] is True

    reloaded = load_graph(graph_path)
    by_id = {t.id: t for t in reloaded.tasks}
    assert by_id["task-a"].status == TaskStatus.READY
    assert by_id["task-b"].status == TaskStatus.PENDING


def test_apply_schedule_409_for_draft_graph(client, graph_path):
    _wire(client, graph_path, _make_graph(status=GraphStatus.DRAFT))
    response = client.post("/api/tasks/schedule")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/tasks/{task_id}/execute
# ---------------------------------------------------------------------------

def test_execute_unknown_task_returns_404(client, graph_path):
    _wire(client, graph_path, _make_graph(status=GraphStatus.APPROVED))
    response = client.post("/api/tasks/does-not-exist/execute")
    assert response.status_code == 404


def test_execute_rejects_non_ready_task(client, graph_path):
    _wire(client, graph_path, _make_graph(status=GraphStatus.APPROVED))
    response = client.post("/api/tasks/task-a/execute")
    assert response.status_code == 409
    assert "expected 'ready'" in response.json()["detail"]


def test_execute_happy_path_records_real_evidence(client, graph_path):
    tasks = [
        Task(id="task-a", node_id="svc-a", title="Build A", status=TaskStatus.READY),
        Task(id="task-b", node_id="svc-b", title="Build B", depends_on=["task-a"]),
    ]
    _wire(
        client,
        graph_path,
        _make_graph(status=GraphStatus.APPROVED, tasks=tasks),
    )
    client.app.dependency_overrides[get_coding_agent] = lambda: _FakeAgent()
    client.app.dependency_overrides[
        get_verification_command_builder
    ] = lambda: _pass_cmd

    response = client.post("/api/tasks/task-a/execute")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["final_status"] == "verified"
    assert body["agent"]["is_fixture"] is False
    assert body["verification"]["passed"] is True
    assert body["verification"]["exit_code"] == 0
    assert body["execution"]["agent_reported_success"] is True

    reloaded = load_graph(graph_path)
    by_id = {t.id: t for t in reloaded.tasks}
    assert by_id["task-a"].status == TaskStatus.VERIFIED
    assert by_id["task-a"].execution_ids == [body["execution"]["id"]]
    assert by_id["task-a"].verification_ids == [body["verification"]["id"]]
    assert len(reloaded.executions) == 1
    assert len(reloaded.verifications) == 1


def test_execute_failed_verification_sets_failed(client, graph_path):
    tasks = [
        Task(id="task-a", node_id="svc-a", title="Build A", status=TaskStatus.READY),
    ]
    _wire(
        client,
        graph_path,
        _make_graph(status=GraphStatus.APPROVED, tasks=tasks),
    )
    client.app.dependency_overrides[get_coding_agent] = lambda: _FakeAgent()
    client.app.dependency_overrides[
        get_verification_command_builder
    ] = lambda: _fail_cmd

    response = client.post("/api/tasks/task-a/execute")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["final_status"] == "failed"
    assert body["verification"]["passed"] is False
    assert body["verification"]["exit_code"] == 1


def test_execute_agent_exception_marks_failed_and_records_execution(client, graph_path):
    tasks = [
        Task(id="task-a", node_id="svc-a", title="Build A", status=TaskStatus.READY),
    ]
    _wire(
        client,
        graph_path,
        _make_graph(status=GraphStatus.APPROVED, tasks=tasks),
    )
    client.app.dependency_overrides[get_coding_agent] = (
        lambda: _FakeAgent(raises=RuntimeError("boom"))
    )
    client.app.dependency_overrides[
        get_verification_command_builder
    ] = lambda: _pass_cmd

    response = client.post("/api/tasks/task-a/execute")
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["task_id"] == "task-a"
    assert "RuntimeError" in detail["error_message"]

    reloaded = load_graph(graph_path)
    by_id = {t.id: t for t in reloaded.tasks}
    assert by_id["task-a"].status == TaskStatus.FAILED
    assert len(reloaded.executions) == 1
    assert reloaded.executions[0].error is not None
    assert len(reloaded.verifications) == 0


def test_execute_fixture_labelling_is_visible_in_response(client, graph_path):
    tasks = [
        Task(id="task-a", node_id="svc-a", title="Build A", status=TaskStatus.READY),
    ]
    _wire(
        client,
        graph_path,
        _make_graph(status=GraphStatus.APPROVED, tasks=tasks),
    )
    client.app.dependency_overrides[get_coding_agent] = lambda: FixtureCodingAgent()
    client.app.dependency_overrides[
        get_verification_command_builder
    ] = lambda: _pass_cmd

    response = client.post("/api/tasks/task-a/execute")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent"]["is_fixture"] is True
    assert body["agent"]["name"] == "coding-agent-fixture-replay"
    assert body["final_status"] == "verified"