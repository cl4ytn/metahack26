import pytest
from pydantic import ValidationError

from backend.app.models.graph import (
    SCHEMA_VERSION,
    ArchitectureGraph,
    Edge,
    GraphStatus,
    Node,
    Task,
    TaskStatus,
    VerificationOutcome,
    VerificationResult,
)


def make_graph() -> ArchitectureGraph:
    return ArchitectureGraph(
        project_name="Demo",
        requirement="Build a todo API",
        nodes=[
            Node(id="db", name="Database", type="database"),
            Node(id="api", name="Todo API", type="api", files=["app/api.py"]),
        ],
        edges=[Edge(id="e1", source="api", target="db", type="reads_from")],
        tasks=[
            Task(id="t1", title="Create DB", node_id="db"),
            Task(id="t2", title="Create API", node_id="api", depends_on=["t1"]),
        ],
    )


def test_defaults():
    g = make_graph()
    assert g.schema_version == SCHEMA_VERSION
    assert g.status == GraphStatus.DRAFT
    assert g.tasks[0].status == TaskStatus.PENDING
    assert g.approved_at is None


def test_json_round_trip_is_lossless():
    g = make_graph()
    data = g.model_dump(mode="json")
    assert ArchitectureGraph.model_validate(data) == g


@pytest.mark.parametrize("bad_id", ["", "1abc", "has space", "a/b", "x" * 65])
def test_invalid_ids_rejected(bad_id):
    with pytest.raises(ValidationError):
        Node(id=bad_id, name="N", type="module")


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Node(id="n1", name="N", type="module", colour="red")


def test_unknown_enum_values_rejected():
    with pytest.raises(ValidationError):
        Node(id="n1", name="N", type="spaceship")
    with pytest.raises(ValidationError):
        Task(id="t1", title="T", node_id="n1", status="done")


def test_wrong_schema_version_rejected():
    with pytest.raises(ValidationError):
        ArchitectureGraph(project_name="P", schema_version="9.9")


def test_empty_title_rejected():
    with pytest.raises(ValidationError):
        Task(id="t1", title="   ", node_id="n1")


def test_cross_record_problems_are_left_to_validator():
    # Duplicate IDs and dangling references must still load, so the
    # validator can report them with actionable messages.
    g = ArchitectureGraph(
        project_name="P",
        nodes=[Node(id="n1", name="A", type="module"), Node(id="n1", name="B", type="module")],
        tasks=[Task(id="t1", title="T", node_id="missing", depends_on=["ghost"])],
    )
    assert len(g.nodes) == 2


def test_passed_verification_requires_exit_code_zero():
    with pytest.raises(ValidationError):
        VerificationResult(
            id="v1", task_id="t1", execution_id="x1", command="pytest",
            outcome=VerificationOutcome.PASSED, exit_code=1,
        )
    with pytest.raises(ValidationError):
        VerificationResult(
            id="v1", task_id="t1", execution_id="x1", command="pytest",
            outcome=VerificationOutcome.PASSED, exit_code=None,
        )
    ok = VerificationResult(
        id="v1", task_id="t1", execution_id="x1", command="pytest",
        outcome=VerificationOutcome.PASSED, exit_code=0,
    )
    assert ok.passed


def test_infrastructure_error_may_have_no_exit_code():
    v = VerificationResult(
        id="v1", task_id="t1", execution_id="x1", command="pytest",
        outcome=VerificationOutcome.INFRASTRUCTURE_ERROR, stderr="pytest not found",
    )
    assert not v.passed and v.exit_code is None