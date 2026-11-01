"""Tests for POST /api/architecture/refine."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api.architecture import get_muse_spark
from backend.app.main import app
from backend.app.models.graph import GraphStatus
from backend.app.services.muse_spark import (
    FixtureMuseSpark,
    MuseSparkOutputError,
    MuseSparkUnavailableError,
)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _draft_graph():
    return FixtureMuseSpark().generate_graph("bookmarks")


def _post_refine(client: TestClient, instruction: str, graph):
    return client.post(
        "/api/architecture/refine",
        json={
            "instruction": instruction,
            "current_graph": graph.model_dump(mode="json"),
        },
    )


def test_refine_add_auth_happy_path(client):
    graph = _draft_graph()
    response = _post_refine(client, "add auth", graph)
    assert response.status_code == 200, response.text

    body = response.json()
    refined = body["graph"]
    assert "svc-auth" in {n["id"] for n in refined["nodes"]}
    assert "edge-api-depends-auth" in {e["id"] for e in refined["edges"]}
    assert "task-auth" in {t["id"] for t in refined["tasks"]}

    history = refined["refinement_history"]
    assert len(history) == 1
    turn = history[0]
    assert turn["instruction"] == "add auth"
    assert "svc-auth" in turn["node_ids_added"]
    assert "edge-api-depends-auth" in turn["edge_ids_added"]
    assert "task-auth" in turn["task_ids_added"]

    assert body["adapter"]["is_fixture"] is True
    assert body["validation"]["is_valid"] is True


def test_refine_blank_instruction_returns_422(client):
    graph = _draft_graph()
    for instruction in ("", "   "):
        response = _post_refine(client, instruction, graph)
        assert response.status_code == 422, (instruction, response.text)


def test_refine_non_draft_returns_409(client):
    graph = _draft_graph()
    approved = graph.model_copy(update={"status": GraphStatus.APPROVED})
    response = _post_refine(client, "add auth", approved)
    assert response.status_code == 409, response.text


def test_refine_schema_1_0_returns_422(client):
    graph = _draft_graph()
    legacy = graph.model_copy(update={"schema_version": "1.0"})
    response = _post_refine(client, "add auth", legacy)
    assert response.status_code == 422, response.text


class _RaisingAdapter:
    def __init__(self, exc):
        self._exc = exc

    def name(self):
        return "raising"

    def is_fixture(self):
        return False

    def generate_graph(self, requirement):
        raise self._exc

    def refine_graph(self, current, instruction):
        raise self._exc


def test_refine_output_error_returns_502(client):
    app.dependency_overrides[get_muse_spark] = lambda: _RaisingAdapter(
        MuseSparkOutputError("bad output")
    )
    response = _post_refine(client, "add auth", _draft_graph())
    assert response.status_code == 502, response.text


def test_refine_unavailable_returns_503(client):
    app.dependency_overrides[get_muse_spark] = lambda: _RaisingAdapter(
        MuseSparkUnavailableError("down")
    )
    response = _post_refine(client, "add auth", _draft_graph())
    assert response.status_code == 503, response.text


def test_refine_rename_to_same_id_returns_502(client):
    """Regression: `rename X to X` must be rejected as an output error (502),
    not silently accepted as an empty-turn no-op."""
    graph = _draft_graph()
    response = _post_refine(client, "rename svc-api to svc-api", graph)
    assert response.status_code == 502, response.text


class _EchoAdapter:
    def __init__(self, graph):
        self._graph = graph

    def name(self):
        return "echo"

    def is_fixture(self):
        return False

    def generate_graph(self, requirement):
        return self._graph

    def refine_graph(self, current, instruction):
        return self._graph


def test_refine_response_shape_and_is_fixture_echo(client):
    app.dependency_overrides[get_muse_spark] = lambda: _EchoAdapter(_draft_graph())
    response = _post_refine(client, "add auth", _draft_graph())
    assert response.status_code == 200, response.text

    body = response.json()
    assert set(body.keys()) == {"graph", "validation", "adapter"}
    assert body["adapter"] == {"name": "echo", "is_fixture": False}