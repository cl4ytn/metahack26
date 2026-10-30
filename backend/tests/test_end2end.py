"""HTTP-level end-to-end integration test for the GraphPilot pipeline.

Codifies (as a repeatable test) what was proven manually via curl in s13:

  approved fixture graph on disk
    -> GET    /api/tasks                (ready/waiting as expected)
    -> POST   /api/tasks/schedule       (promote zero-dep tasks)
    -> POST   /api/tasks/{id}/execute   (per task: real subprocess, verified)
    -> repeat schedule+execute along the DAG until all tasks are verified
    -> final state: every task verified, nothing ready/blocked/waiting

Honesty notes baked into the assertions:
- Every "verified" is asserted to come from a real subprocess exiting 0
  (verification.outcome == "passed", exit_code == 0), never from the
  agent's claim (agent_reported_success is stored but not consulted).
- Fixture labelling is asserted to be present in the response body
  (agent.is_fixture is True), not only in logs.

Isolation: this test rewrites the real backend/architecture.yaml (the only
place the default seam will find it) and restores the original bytes on
teardown. Not parallel-safe against itself or against a live demo run --
run it when the API is idle. The fixture coding agent writes
backend/src/task-*.py; those files are removed on teardown, but only the
ones this test created.

NOT EXECUTED as of the session this file was written. Run from repo root:
    python -m pytest backend/tests/test_pipeline_end_to_end.py -v
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.models.graph import GraphStatus
from backend.app.services.muse_spark import FixtureMuseSpark
from backend.app.storage.yaml_store import save_graph

ARCH_PATH = Path("backend/architecture.yaml")
SRC_DIR = Path("backend/src")

FIXTURE_TASK_IDS = (
    "task-db-schema",
    "task-slug",
    "task-link-service",
    "task-api",
    "task-web-ui",
)


@pytest.fixture
def fresh_approved_architecture(tmp_path):
    """Swap in a fresh approved fixture graph, then restore the previous state.

    Backs up the existing backend/architecture.yaml if present; writes a
    freshly-fixtured graph with status=APPROVED; on teardown restores the
    backup (or deletes the file if there was none) and removes any
    backend/src/task-*.py that this test caused the fixture agent to write.
    """
    backup: Path | None = None
    if ARCH_PATH.exists():
        backup = tmp_path / "architecture.yaml.bak"
        shutil.copy2(ARCH_PATH, backup)

    pre_existing_src: set[str] = set()
    if SRC_DIR.exists():
        pre_existing_src = {p.name for p in SRC_DIR.iterdir() if p.is_file()}

    graph = FixtureMuseSpark().generate_graph(
        "a bookmark manager with slug generation"
    )
    approved = graph.model_copy(update={"status": GraphStatus.APPROVED})
    save_graph(approved, ARCH_PATH)

    try:
        yield
    finally:
        if backup is not None:
            shutil.copy2(backup, ARCH_PATH)
        elif ARCH_PATH.exists():
            ARCH_PATH.unlink()

        if SRC_DIR.exists():
            for p in SRC_DIR.iterdir():
                if p.is_file() and p.name not in pre_existing_src:
                    p.unlink()


def _assert_verified_execute_response(body: dict, task_id: str) -> None:
    """Assert the execute response shows a genuinely-verified outcome."""
    assert body["task_id"] == task_id
    assert body["final_status"] == "verified"
    # The agent's report is echoed, but never the ground for "verified":
    assert body["agent"]["name"] == "coding-agent-fixture-replay"
    assert body["agent"]["is_fixture"] is True
    # The verification record must show a real subprocess that exited 0:
    verification = body["verification"]
    assert verification["outcome"] == "passed"
    assert verification["passed"] is True
    assert verification["exit_code"] == 0
    assert task_id in verification["command"]
    # And the demo command really ran (fixture command prints this):
    assert task_id in verification["stdout"]
    assert body["saved"] is True


def test_full_pipeline_end_to_end(fresh_approved_architecture):
    client = TestClient(create_app())

    # 1. Listing: approved, schedulable, correct initial ready/waiting split.
    listing = client.get("/api/tasks")
    assert listing.status_code == 200
    body = listing.json()
    assert body["schedulable"] is True
    assert body["graph_status"] == "approved"
    ready = {t["id"] for t in body["tasks"] if t["schedule"] == "ready"}
    waiting = {t["id"] for t in body["tasks"] if t["schedule"] == "waiting"}
    blocked = {t["id"] for t in body["tasks"] if t["schedule"] == "blocked"}
    assert ready == {"task-db-schema", "task-slug"}
    assert waiting == {"task-link-service", "task-api", "task-web-ui"}
    assert blocked == set()

    # 2. First schedule: exactly the two zero-dep tasks move pending -> ready.
    first = client.post("/api/tasks/schedule")
    assert first.status_code == 200
    first_body = first.json()
    transitioned = {(t["task_id"], t["to_status"]) for t in first_body["transitioned"]}
    assert transitioned == {
        ("task-db-schema", "ready"),
        ("task-slug", "ready"),
    }
    assert first_body["saved"] is True

    # 3. Execute both ready tasks; each must come back verified.
    for task_id in ("task-db-schema", "task-slug"):
        resp = client.post(f"/api/tasks/{task_id}/execute")
        assert resp.status_code == 200, resp.text
        _assert_verified_execute_response(resp.json(), task_id)

    # 4. Next schedule promotes exactly one more task.
    second = client.post("/api/tasks/schedule").json()
    promoted = [t["task_id"] for t in second["transitioned"]]
    assert promoted == ["task-link-service"]

    # 5. Finish the chain: schedule-then-execute for the remaining three.
    for task_id in ("task-link-service", "task-api", "task-web-ui"):
        sched = client.post("/api/tasks/schedule")
        assert sched.status_code == 200
        ready_now = set(sched.json()["ready"])
        assert task_id in ready_now, (task_id, ready_now)
        resp = client.post(f"/api/tasks/{task_id}/execute")
        assert resp.status_code == 200, resp.text
        _assert_verified_execute_response(resp.json(), task_id)

    # 6. Final state: all five verified, nothing left schedulable.
    final_listing = client.get("/api/tasks").json()
    statuses = {t["id"]: t["status"] for t in final_listing["tasks"]}
    assert statuses == {tid: "verified" for tid in FIXTURE_TASK_IDS}
    final_sched = client.post("/api/tasks/schedule").json()
    assert final_sched["transitioned"] == []
    assert final_sched["ready"] == []
    assert final_sched["blocked"] == []
    assert final_sched["waiting"] == []


def test_execute_rejects_non_ready_task(fresh_approved_architecture):
    """A pending (never-scheduled) task must not be executed: 409, no state change."""
    client = TestClient(create_app())

    # task-api depends on task-link-service, which is pending -> not ready.
    resp = client.post("/api/tasks/task-api/execute")
    assert resp.status_code == 409

    # Nothing moved:
    after = client.get("/api/tasks").json()
    assert all(t["status"] == "pending" for t in after["tasks"])


def test_arch_generation_returns_valid_fixture_and_does_not_persist(
    fresh_approved_architecture,
):
    """POST /api/architecture returns a valid fixture graph and leaves the file alone."""
    client = TestClient(create_app())
    before = ARCH_PATH.read_bytes()

    resp = client.post(
        "/api/architecture",
        json={"requirement": "anything goes here"},
    )
    assert resp.status_code == 200
    body = resp.json()

    # Fixture labelling in the response body, not just logs:
    assert body["adapter"]["name"] == "muse-spark-fixture-replay"
    assert body["adapter"]["is_fixture"] is True
    # Fixture graph is valid but NOT approved (fresh draft):
    assert body["validation"]["is_valid"] is True
    assert body["validation"]["errors"] == []
    assert body["graph"]["status"] == "draft"

    # And POST did NOT persist (approved graph on disk is untouched):
    assert ARCH_PATH.read_bytes() == before