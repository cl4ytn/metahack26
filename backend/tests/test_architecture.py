from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.architecture import get_architecture_path, get_muse_spark, router
from backend.app.models.graph import ArchitectureGraph, Node, NodeType
from backend.app.storage.yaml_store import save_graph


class FakeAdapter:
    def __init__(self, graph, *, name="fake-adapter", is_fixture=True):
        self._graph = graph
        self._name = name
        self._is_fixture = is_fixture
        self.calls = []

    def name(self):
        return self._name

    def is_fixture(self):
        return self._is_fixture

    def generate_graph(self, requirement):
        self.calls.append(requirement)
        return self._graph


def make_client(overrides=None, *, raise_server_exceptions=True):
    app = FastAPI()
    app.include_router(router)
    for dependency, provider in (overrides or {}).items():
        app.dependency_overrides[dependency] = provider
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def test_post_default_fixture_labels_response_and_validates():
    client = make_client()

    response = client.post(
        "/api/architecture",
        json={"requirement": "Build a bookmarks service"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["adapter"]["name"] == "muse-spark-fixture-replay"
    assert body["adapter"]["is_fixture"] is True
    assert body["validation"]["is_valid"] is True
    assert body["validation"]["errors"] == []
    assert body["graph"]["status"] == "draft"
    assert body["graph"]["approved_at"] is None


def test_post_uses_adapter_and_returns_graph_report_metadata():
    graph = ArchitectureGraph(project_name="demo", requirement="original")
    fake = FakeAdapter(graph, name="fake-adapter", is_fixture=True)
    client = make_client({get_muse_spark: lambda: fake})

    response = client.post(
        "/api/architecture",
        json={"requirement": "  Build demo  "},
    )

    assert response.status_code == 200
    body = response.json()
    assert fake.calls == ["  Build demo  "]
    assert body["graph"]["project_name"] == "demo"
    assert body["adapter"] == {"name": "fake-adapter", "is_fixture": True}
    assert body["validation"] == {"is_valid": True, "errors": []}


def test_post_returns_validation_errors_without_hiding_graph():
    graph = ArchitectureGraph(
        project_name="demo",
        nodes=[
            Node(id="node-1", type=NodeType.SERVICE, name="A"),
            Node(id="node-1", type=NodeType.SERVICE, name="B"),
        ],
    )
    fake = FakeAdapter(graph)
    client = make_client({get_muse_spark: lambda: fake})

    response = client.post(
        "/api/architecture",
        json={"requirement": "Build demo"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["graph"]["nodes"][0]["id"] == "node-1"
    assert body["validation"]["is_valid"] is False
    assert any(issue["code"] == "duplicate_id" for issue in body["validation"]["errors"])


def test_post_rejects_blank_requirement_before_adapter_call():
    fake = FakeAdapter(ArchitectureGraph(project_name="demo"))
    client = make_client({get_muse_spark: lambda: fake})

    response = client.post(
        "/api/architecture",
        json={"requirement": "   "},
    )

    assert response.status_code == 422
    assert fake.calls == []


def test_get_returns_saved_graph(tmp_path):
    path = tmp_path / "architecture.yaml"
    graph = ArchitectureGraph(project_name="stored")
    save_graph(graph, path)
    client = make_client({get_architecture_path: lambda: path})

    response = client.get("/api/architecture")

    assert response.status_code == 200
    assert response.json()["project_name"] == "stored"


def test_get_missing_graph_returns_404(tmp_path):
    path = tmp_path / "missing.yaml"
    client = make_client({get_architecture_path: lambda: path})

    response = client.get("/api/architecture")

    assert response.status_code == 404


def test_get_unreadable_graph_returns_500(tmp_path):
    path = tmp_path / "architecture.yaml"
    path.write_text("project_name: [unterminated")
    client = make_client(
        {get_architecture_path: lambda: path},
        raise_server_exceptions=False,
    )

    response = client.get("/api/architecture")

    assert response.status_code == 500