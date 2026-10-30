"""Tests for POST /api/architecture/approve."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api.architecture import get_architecture_path
from backend.app.main import create_app
from backend.app.models.graph import (
    ArchitectureGraph,
    GraphStatus,
    Node,
    NodeType,
    Task,
)
from backend.app.services.validator import validate_graph
from backend.app.storage.yaml_store import InvalidGraphError, load_graph


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def architecture_path(tmp_path):
    return tmp_path / "architecture.yaml"


def _valid_graph(project_name: str = "bookmarks-service") -> ArchitectureGraph:
    node = Node(id="svc-api", name="API", type=NodeType.SERVICE)
    task = Task(id="task-a", title="First task", node_id="svc-api")
    return ArchitectureGraph(
        project_name=project_name,
        nodes=[node],
        tasks=[task],
    )


def _invalid_graph() -> ArchitectureGraph:
    n1 = Node(id="dup", name="One", type=NodeType.SERVICE)
    n2 = Node(id="dup", name="Two", type=NodeType.MODULE)
    return ArchitectureGraph(project_name="bad", nodes=[n1, n2])


def _payload(graph: ArchitectureGraph) -> dict:
    return graph.model_dump(mode="json")


def test_approve_valid_graph_persists(app, client, architecture_path):
    app.dependency_overrides[get_architecture_path] = lambda: architecture_path
    try:
        resp = client.post(
            "/api/architecture/approve",
            json=_payload(_valid_graph()),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["saved"] is True
        assert body["saved_path"] == str(architecture_path)
        assert body["graph"]["status"] == "approved"
        assert body["graph"]["approved_at"] is not None
        assert body["validation"]["is_valid"] is True

        assert architecture_path.exists()
        on_disk = load_graph(architecture_path)
        assert on_disk.status == GraphStatus.APPROVED
        assert on_disk.approved_at is not None
    finally:
        app.dependency_overrides.clear()


def test_approve_invalid_graph_returns_422_and_writes_nothing(
    app, client, architecture_path
):
    app.dependency_overrides[get_architecture_path] = lambda: architecture_path
    try:
        resp = client.post(
            "/api/architecture/approve",
            json=_payload(_invalid_graph()),
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert isinstance(detail, list) and detail
        assert not architecture_path.exists()
    finally:
        app.dependency_overrides.clear()


def test_approve_save_failure_returns_409_and_writes_nothing(
    app, client, architecture_path, monkeypatch
):
    app.dependency_overrides[get_architecture_path] = lambda: architecture_path
    try:
        bad_report = validate_graph(_invalid_graph())
        error = InvalidGraphError(architecture_path, bad_report)

        def _fail_save(graph, path):
            raise error

        monkeypatch.setattr(
            "backend.app.api.architecture.save_graph",
            _fail_save,
        )

        resp = client.post(
            "/api/architecture/approve",
            json=_payload(_valid_graph()),
        )
        assert resp.status_code == 409, resp.text
        assert not architecture_path.exists()
    finally:
        app.dependency_overrides.clear()