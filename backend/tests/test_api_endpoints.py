import sys
import pytest
import asyncio
import httpx
from backend.main import app
from backend.app.api import architecture
from backend.app.services.muse_spark import FixtureMuseSpark

class ASGIClient:
    """Use HTTPX's native ASGI transport without a synchronous portal thread."""
    def request(self, method, url, **kwargs):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as session:
                return await asyncio.wait_for(session.request(method, url, **kwargs), timeout=40)
        return asyncio.run(send())
    def get(self, url, **kwargs): return self.request("GET", url, **kwargs)
    def post(self, url, **kwargs): return self.request("POST", url, **kwargs)
    def put(self, url, **kwargs): return self.request("PUT", url, **kwargs)

client = ASGIClient()

@pytest.fixture(autouse=True)
def isolated_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(architecture, "YAML_PATH", tmp_path / "architecture.yaml")
    architecture.set_current_graph(FixtureMuseSpark().generate_graph("fixture"))


def verify(task="task-db-schema", **kw):
    return client.post(f"/api/tasks/{task}/verify", json=kw)


def test_decompose_persists_explicit_fixture():
    data = client.post("/api/requirements/decompose", json={"requirement": "custom request"}).json()
    assert data["is_fixture"] and "no model" in data["provenance"]
    assert client.get("/api/architecture").json() == data["graph"]
    assert architecture.YAML_PATH.exists()


def test_approval_and_no_fabricated_verification():
    assert verify(command=[sys.executable, "-c", "pass"]).status_code == 409
    assert client.post("/api/architecture/approve").status_code == 200
    assert verify().status_code == 400
    assert verify(simulate_failure=True).status_code == 400
    assert verify("task-link-service", command=[sys.executable, "-c", "pass"]).status_code == 409
    assert client.post("/api/tasks/task-db-schema/status", json={"status": "verified"}).status_code == 400


def test_real_command_failure_recovery_and_reset(tmp_path):
    # The subprocess imports and tests actual project code, then reruns after a repair.
    (tmp_path / "feature.py").write_text("def answer(): return 0\n")
    (tmp_path / "check.py").write_text("from feature import answer\nassert answer() == 42\nprint('answer criterion passed')\n")
    client.post("/api/architecture/approve")
    payload = {"command": [sys.executable, "check.py"], "project_path": str(tmp_path)}
    failed = verify(**payload).json()
    assert failed["new_status"] == "failed" and failed["exit_code"] != 0
    assert "task-link-service" in failed["impacted_blocked_tasks"]
    (tmp_path / "feature.py").write_text("def answer(): return 42\n")
    passed = verify(**payload).json()
    assert passed["passed"] and "answer criterion passed" in passed["stdout"]
    assert passed["verification"]["project_path"] == str(tmp_path.resolve())
    assert passed["verification"]["graph_revision"] == passed["graph"]["revision"]
    passed = verify("task-slug", **payload).json()
    statuses = {t["id"]: t["status"] for t in passed["graph"]["tasks"]}
    assert statuses["task-link-service"] == "ready"
    reset = client.post("/api/tasks/task-db-schema/reset").json()
    assert next(t for t in reset["graph"]["tasks"] if t["id"] == "task-link-service")["status"] == "pending"


def test_semantic_edit_invalidates_exact_approval_and_ignores_status_tampering():
    approved = client.post("/api/architecture/approve").json()
    forged = dict(approved)
    forged["tasks"][0]["status"] = "verified"
    unchanged = client.put("/api/architecture", json=forged).json()
    assert unchanged["tasks"][0]["status"] != "verified"
    forged["nodes"][0]["name"] = "Edited component"
    edited = client.put("/api/architecture", json=forged).json()
    assert edited["status"] == "draft" and edited["approved_revision"] is None
    assert edited["revision"] == approved["revision"] + 1
    assert verify(command=[sys.executable, "-c", "pass"]).status_code == 409
    assert client.post("/api/architecture/approve").json()["approved_revision"] == edited["revision"]
