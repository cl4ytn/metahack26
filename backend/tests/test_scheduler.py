from types import SimpleNamespace

import pytest

from backend.app.models.graph import (
    ArchitectureGraph,
    GraphStatus,
    Node,
    NodeType,
    Task,
    TaskStatus,
)
from backend.app.services import scheduler
from backend.app.services.scheduler import (
    GraphNotApprovedError,
    SchedulePlan,
    SchedulerError,
    UnschedulableGraphError,
    build_schedule,
)

S = TaskStatus


def make_graph(specs, status=GraphStatus.APPROVED):
    """specs: list of (task_id, task_status, [dependency ids])."""
    return ArchitectureGraph(
        project_name="demo",
        status=status,
        nodes=[Node(id="n1", type=NodeType.MODULE, name="n1")],
        tasks=[
            Task(id=tid, node_id="n1", title=tid, status=st, depends_on=deps)
            for tid, st, deps in specs
        ],
    )


@pytest.fixture
def stub_validator(monkeypatch):
    """Isolate scheduling logic from the validator (needed for verified tasks,
    whose valid construction requires VerificationResult fields not yet known)."""
    monkeypatch.setattr(
        scheduler, "validate_graph", lambda g: SimpleNamespace(is_valid=True, errors=[])
    )


# --- tests using the REAL validator (no verified tasks involved) ---


def test_no_dependencies_is_ready():
    plan = build_schedule(make_graph([("a", S.PENDING, [])]))
    assert plan == SchedulePlan(ready=("a",), blocked=(), waiting=())


def test_draft_graph_is_refused():
    g = make_graph([("a", S.PENDING, [])], status=GraphStatus.DRAFT)
    with pytest.raises(GraphNotApprovedError):
        build_schedule(g)


def test_invalid_graph_is_refused_not_partially_scheduled():
    g = make_graph([("a", S.PENDING, []), ("a", S.PENDING, [])])  # duplicate id
    with pytest.raises(UnschedulableGraphError) as exc:
        build_schedule(g)
    assert exc.value.report.is_valid is False


def test_cycle_is_refused():
    g = make_graph([("a", S.PENDING, ["b"]), ("b", S.PENDING, ["a"])])
    with pytest.raises(UnschedulableGraphError):
        build_schedule(g)


def test_errors_share_a_base_class():
    assert issubclass(UnschedulableGraphError, SchedulerError)
    assert issubclass(GraphNotApprovedError, SchedulerError)


def test_input_graph_not_mutated():
    g = make_graph([("a", S.PENDING, []), ("b", S.PENDING, ["a"])])
    before = g.model_dump()
    build_schedule(g)
    assert g.model_dump() == before


def test_result_is_deterministic():
    g = make_graph([("c", S.PENDING, []), ("a", S.PENDING, []), ("b", S.PENDING, ["a"])])
    assert build_schedule(g) == build_schedule(g)


def test_ready_order_is_declaration_order():
    g = make_graph([("c", S.PENDING, []), ("a", S.PENDING, []), ("b", S.PENDING, [])])
    assert build_schedule(g).ready == ("c", "a", "b")


def test_unverified_dependency_waits():
    g = make_graph([("a", S.PENDING, []), ("b", S.PENDING, ["a"])])
    plan = build_schedule(g)
    assert plan.ready == ("a",)
    assert plan.waiting == ("b",)


# --- tests with the validator stubbed (status logic only) ---


def test_verified_dependency_makes_task_ready(stub_validator):
    g = make_graph([("a", S.VERIFIED, []), ("b", S.PENDING, ["a"])])
    assert build_schedule(g) == SchedulePlan(ready=("b",), blocked=(), waiting=())


@pytest.mark.parametrize("dep_status", [S.RUNNING, S.IMPLEMENTED, S.VERIFYING])
def test_in_flight_dependency_is_not_verified(stub_validator, dep_status):
    g = make_graph([("a", dep_status, []), ("b", S.PENDING, ["a"])])
    plan = build_schedule(g)
    assert plan.waiting == ("b",)
    assert plan.ready == ()


@pytest.mark.parametrize("dep_status", [S.FAILED, S.BLOCKED])
def test_failed_or_blocked_dependency_blocks(stub_validator, dep_status):
    g = make_graph([("a", dep_status, []), ("b", S.PENDING, ["a"])])
    assert build_schedule(g).blocked == ("b",)


def test_blocking_is_transitive(stub_validator):
    g = make_graph(
        [("a", S.FAILED, []), ("b", S.PENDING, ["a"]), ("c", S.PENDING, ["b"])]
    )
    assert build_schedule(g).blocked == ("b", "c")


def test_one_bad_dependency_blocks_despite_other_verified(stub_validator):
    g = make_graph(
        [("a", S.VERIFIED, []), ("b", S.FAILED, []), ("c", S.PENDING, ["a", "b"])]
    )
    assert build_schedule(g).blocked == ("c",)


def test_already_ready_task_is_reported_ready(stub_validator):
    g = make_graph([("a", S.READY, [])])
    assert build_schedule(g).ready == ("a",)


def test_ready_task_with_unverified_dependency_is_demoted_to_waiting(stub_validator):
    g = make_graph([("a", S.PENDING, []), ("b", S.READY, ["a"])])
    plan = build_schedule(g)
    assert plan.waiting == ("b",)
    assert "b" not in plan.ready


@pytest.mark.parametrize(
    "st", [S.RUNNING, S.IMPLEMENTED, S.VERIFYING, S.VERIFIED, S.FAILED, S.BLOCKED]
)
def test_non_schedulable_statuses_are_not_classified(stub_validator, st):
    plan = build_schedule(make_graph([("a", st, [])]))
    assert plan == SchedulePlan(ready=(), blocked=(), waiting=())


def test_mixed_graph(stub_validator):
    g = make_graph(
        [
            ("db", S.VERIFIED, []),
            ("api", S.PENDING, ["db"]),
            ("ui", S.PENDING, ["api"]),
            ("bad", S.FAILED, []),
            ("report", S.PENDING, ["bad"]),
            ("docs", S.PENDING, []),
        ]
    )
    plan = build_schedule(g)
    assert plan.ready == ("api", "docs")
    assert plan.waiting == ("ui",)
    assert plan.blocked == ("report",)