"""Tests for app.services.validator.

Evidence records (ExecutionResult / VerificationResult) are built with
model_construct so these tests do not depend on which of their fields are
required; the validator only reads id, task_id, execution_id and outcome.
"""

import pytest

from backend.app.models.graph import (
    ArchitectureGraph,
    Edge,
    ExecutionResult,
    Node,
    Task,
    VerificationOutcome,
    VerificationResult,
)
from backend.app.services import validator
from backend.app.services.validator import validate_graph


# ---- builders -------------------------------------------------------------


def node(i):
    return Node(id=i, name=i.upper(), type="module")


def edge(i, source, target):
    return Edge(id=i, source=source, target=target, type="calls")


def task(i, node_id="n1", depends_on=(), status="pending",
         execution_ids=(), verification_ids=()):
    return Task(
        id=i,
        title=f"Task {i}",
        node_id=node_id,
        depends_on=list(depends_on),
        status=status,
        execution_ids=list(execution_ids),
        verification_ids=list(verification_ids),
    )


def execution(i, task_id):
    return ExecutionResult.model_construct(id=i, task_id=task_id)


def verification(i, task_id, execution_id=None, outcome="passed"):
    return VerificationResult.model_construct(
        id=i,
        task_id=task_id,
        execution_id=execution_id,
        command="pytest",
        outcome=VerificationOutcome(outcome),
        exit_code=0 if outcome == "passed" else 1,
    )


def graph(**kw):
    kw.setdefault("project_name", "P")
    return ArchitectureGraph(**kw)


def valid_graph(**overrides):
    kw = dict(
        nodes=[node("n1"), node("n2")],
        edges=[edge("e1", "n1", "n2")],
        tasks=[
            task("t1", "n1", status="verified",
                 execution_ids=["x1"], verification_ids=["v1"]),
            task("t2", "n2", depends_on=["t1"], status="ready"),
        ],
        executions=[execution("x1", "t1")],
        verifications=[verification("v1", "t1", "x1")],
    )
    kw.update(overrides)
    return graph(**kw)


def codes(report):
    return [e.code for e in report.errors]


# ---- valid graphs ---------------------------------------------------------


def test_empty_graph_is_valid():
    report = validate_graph(graph())
    assert report.is_valid
    assert report.errors == []


def test_minimal_graph_is_valid():
    g = graph(nodes=[node("n1")], tasks=[task("t1")])
    assert validate_graph(g).is_valid


def test_full_valid_graph_is_valid():
    assert validate_graph(valid_graph()).is_valid


def test_diamond_dependencies_are_not_a_cycle():
    g = graph(
        nodes=[node("n1")],
        tasks=[
            task("a"),
            task("b", depends_on=["a"]),
            task("c", depends_on=["a"]),
            task("d", depends_on=["b", "c"]),
        ],
    )
    assert validate_graph(g).is_valid


def test_long_dependency_chain_does_not_hit_recursion_limit():
    n = 3000
    tasks = [task("t0")] + [task(f"t{i}", depends_on=[f"t{i-1}"]) for i in range(1, n)]
    assert validate_graph(graph(nodes=[node("n1")], tasks=tasks)).is_valid


def test_validation_does_not_mutate_graph():
    g = valid_graph(tasks=[task("t1", depends_on=["t1", "ghost"])])
    before = g.model_dump()
    validate_graph(g)
    assert g.model_dump() == before


# ---- duplicate ids --------------------------------------------------------


@pytest.mark.parametrize(
    "entity_type, entity_id, build",
    [
        ("node", "n1", lambda: graph(nodes=[node("n1"), node("n1")])),
        ("edge", "e1", lambda: graph(
            nodes=[node("n1"), node("n2")],
            edges=[edge("e1", "n1", "n2"), edge("e1", "n2", "n1")])),
        ("task", "t1", lambda: graph(nodes=[node("n1")], tasks=[task("t1"), task("t1")])),
        ("execution", "x1", lambda: graph(
            nodes=[node("n1")], tasks=[task("t1")],
            executions=[execution("x1", "t1"), execution("x1", "t1")])),
        ("verification", "v1", lambda: graph(
            nodes=[node("n1")], tasks=[task("t1")],
            verifications=[verification("v1", "t1"), verification("v1", "t1")])),
    ],
)
def test_duplicate_ids_per_entity_type(entity_type, entity_id, build):
    report = validate_graph(build())
    assert codes(report) == [validator.DUPLICATE_ID]
    issue = report.errors[0]
    assert issue.entity_type == entity_type
    assert issue.entity_id == entity_id


def test_same_id_in_different_entity_types_is_allowed():
    g = graph(nodes=[node("x1")], tasks=[task("x1", node_id="x1")])
    assert validate_graph(g).is_valid


# ---- unresolved references -----------------------------------------------


@pytest.mark.parametrize(
    "entity_type, entity_id, field, ref, build",
    [
        ("edge", "e1", "source", "ghost", lambda: graph(
            nodes=[node("n1")], edges=[edge("e1", "ghost", "n1")])),
        ("edge", "e1", "target", "ghost", lambda: graph(
            nodes=[node("n1")], edges=[edge("e1", "n1", "ghost")])),
        ("task", "t1", "node_id", "ghost", lambda: graph(
            tasks=[task("t1", node_id="ghost")])),
        ("task", "t1", "depends_on[0]", "ghost", lambda: graph(
            nodes=[node("n1")], tasks=[task("t1", depends_on=["ghost"])])),
        ("task", "t1", "execution_ids[0]", "ghost", lambda: graph(
            nodes=[node("n1")], tasks=[task("t1", execution_ids=["ghost"])])),
        ("task", "t1", "verification_ids[0]", "ghost", lambda: graph(
            nodes=[node("n1")], tasks=[task("t1", verification_ids=["ghost"])])),
        ("execution", "x1", "task_id", "ghost", lambda: graph(
            nodes=[node("n1")], executions=[execution("x1", "ghost")])),
        ("verification", "v1", "task_id", "ghost", lambda: graph(
            nodes=[node("n1")], tasks=[task("t1")],
            verifications=[verification("v1", "ghost")])),
        ("verification", "v1", "execution_id", "ghost", lambda: graph(
            nodes=[node("n1")], tasks=[task("t1")],
            verifications=[verification("v1", "t1", execution_id="ghost")])),
    ],
)
def test_unresolved_references(entity_type, entity_id, field, ref, build):
    report = validate_graph(build())
    assert codes(report) == [validator.UNRESOLVED_REFERENCE]
    issue = report.errors[0]
    assert (issue.entity_type, issue.entity_id, issue.field, issue.ref_id) == (
        entity_type, entity_id, field, ref)
    assert entity_id in issue.message and ref in issue.message


def test_second_bad_dependency_reports_its_index():
    g = graph(nodes=[node("n1")], tasks=[task("t1"), task("t2", depends_on=["t1", "ghost"])])
    report = validate_graph(g)
    assert [e.field for e in report.errors] == ["depends_on[1]"]


# ---- evidence ownership ---------------------------------------------------


def test_task_listing_another_tasks_execution_is_flagged():
    g = graph(
        nodes=[node("n1")],
        tasks=[task("t1", execution_ids=["x1"]), task("t2")],
        executions=[execution("x1", "t2")],
    )
    report = validate_graph(g)
    assert codes(report) == [validator.EVIDENCE_MISMATCH]
    assert report.errors[0].entity_id == "t1"
    assert report.errors[0].ref_id == "x1"


def test_task_listing_another_tasks_verification_is_flagged():
    g = graph(
        nodes=[node("n1")],
        tasks=[task("t1", verification_ids=["v1"]), task("t2")],
        verifications=[verification("v1", "t2")],
    )
    assert codes(validate_graph(g)) == [validator.EVIDENCE_MISMATCH]


def test_verification_pointing_at_execution_of_another_task_is_flagged():
    g = graph(
        nodes=[node("n1")],
        tasks=[task("t1"), task("t2")],
        executions=[execution("x1", "t2")],
        verifications=[verification("v1", "t1", execution_id="x1")],
    )
    report = validate_graph(g)
    assert codes(report) == [validator.EVIDENCE_MISMATCH]
    assert report.errors[0].entity_type == "verification"


# ---- dependencies ---------------------------------------------------------


def test_self_dependency_is_reported_once_and_not_as_cycle():
    g = graph(nodes=[node("n1")], tasks=[task("t1", depends_on=["t1"])])
    report = validate_graph(g)
    assert codes(report) == [validator.SELF_DEPENDENCY]
    assert report.errors[0].entity_id == "t1"


def test_two_task_cycle():
    g = graph(nodes=[node("n1")], tasks=[
        task("t1", depends_on=["t2"]), task("t2", depends_on=["t1"])])
    report = validate_graph(g)
    assert codes(report) == [validator.DEPENDENCY_CYCLE]
    assert "t1 -> t2 -> t1" in report.errors[0].message


def test_three_task_cycle_shows_concrete_path():
    g = graph(nodes=[node("n1")], tasks=[
        task("t1", depends_on=["t2"]),
        task("t2", depends_on=["t3"]),
        task("t3", depends_on=["t1"]),
    ])
    report = validate_graph(g)
    assert codes(report) == [validator.DEPENDENCY_CYCLE]
    assert "t1 -> t2 -> t3 -> t1" in report.errors[0].message


def test_two_disjoint_cycles_give_two_issues():
    g = graph(nodes=[node("n1")], tasks=[
        task("t1", depends_on=["t2"]), task("t2", depends_on=["t1"]),
        task("t3", depends_on=["t4"]), task("t4", depends_on=["t3"]),
    ])
    report = validate_graph(g)
    assert codes(report) == [validator.DEPENDENCY_CYCLE] * 2
    assert [e.entity_id for e in report.errors] == ["t1", "t3"]


def test_task_downstream_of_a_cycle_is_not_blamed():
    g = graph(nodes=[node("n1")], tasks=[
        task("t0", depends_on=["t1"]),
        task("t1", depends_on=["t2"]),
        task("t2", depends_on=["t1"]),
    ])
    report = validate_graph(g)
    assert codes(report) == [validator.DEPENDENCY_CYCLE]
    assert "t0" not in report.errors[0].message


def test_dangling_dependency_is_not_reported_as_cycle():
    g = graph(nodes=[node("n1")], tasks=[task("t1", depends_on=["ghost"])])
    assert codes(validate_graph(g)) == [validator.UNRESOLVED_REFERENCE]


# ---- verified tasks -------------------------------------------------------


def test_verified_task_without_any_verification():
    g = graph(nodes=[node("n1")], tasks=[task("t1", status="verified")])
    report = validate_graph(g)
    assert codes(report) == [validator.VERIFIED_WITHOUT_EVIDENCE]
    assert report.errors[0].entity_id == "t1"


@pytest.mark.parametrize("outcome", ["failed", "timed_out", "infrastructure_error"])
def test_verified_task_with_non_passing_verification(outcome):
    g = graph(
        nodes=[node("n1")],
        tasks=[task("t1", status="verified", verification_ids=["v1"])],
        verifications=[verification("v1", "t1", outcome=outcome)],
    )
    assert codes(validate_graph(g)) == [validator.VERIFIED_WITHOUT_EVIDENCE]


def test_verified_task_with_passing_result_not_listed_by_task():
    g = graph(
        nodes=[node("n1")],
        tasks=[task("t1", status="verified")],
        verifications=[verification("v1", "t1")],
    )
    assert codes(validate_graph(g)) == [validator.VERIFIED_WITHOUT_EVIDENCE]


def test_verified_task_with_passing_result_from_another_task():
    g = graph(
        nodes=[node("n1")],
        tasks=[task("t1", status="verified", verification_ids=["v1"]), task("t2")],
        verifications=[verification("v1", "t2")],
    )
    assert set(codes(validate_graph(g))) == {
        validator.EVIDENCE_MISMATCH, validator.VERIFIED_WITHOUT_EVIDENCE}


def test_one_passing_result_among_failures_is_enough():
    g = graph(
        nodes=[node("n1")],
        tasks=[task("t1", status="verified", verification_ids=["v1", "v2"])],
        verifications=[verification("v1", "t1", outcome="failed"),
                       verification("v2", "t1")],
    )
    assert validate_graph(g).is_valid


def test_failed_verification_on_unverified_task_is_fine():
    g = graph(
        nodes=[node("n1")],
        tasks=[task("t1", status="failed", verification_ids=["v1"])],
        verifications=[verification("v1", "t1", outcome="failed")],
    )
    assert validate_graph(g).is_valid


# ---- approval -------------------------------------------------------------


def test_approved_valid_graph_is_valid():
    assert validate_graph(valid_graph(status="approved")).is_valid


def test_approved_graph_with_issue_gets_extra_error():
    g = valid_graph(status="approved", tasks=[task("t1", node_id="ghost")])
    report = validate_graph(g)
    assert codes(report) == [validator.UNRESOLVED_REFERENCE, validator.APPROVED_WITH_ISSUES]
    assert "1 integrity issue" in report.errors[-1].message


def test_draft_graph_with_issue_has_no_approval_error():
    g = valid_graph(status="draft", tasks=[task("t1", node_id="ghost")])
    assert validator.APPROVED_WITH_ISSUES not in codes(validate_graph(g))


# ---- collecting everything ------------------------------------------------


def test_all_errors_are_collected_not_just_first():
    g = graph(
        nodes=[node("n1"), node("n1")],                       # duplicate
        edges=[edge("e1", "n1", "ghost")],                    # unresolved
        tasks=[
            task("t1", depends_on=["t1"]),                    # self dependency
            task("t2", depends_on=["t3"]),                    # cycle
            task("t3", depends_on=["t2"]),
            task("t4", status="verified"),                    # no evidence
        ],
    )
    report = validate_graph(g)
    assert not report.is_valid
    assert set(codes(report)) == {
        validator.DUPLICATE_ID,
        validator.UNRESOLVED_REFERENCE,
        validator.SELF_DEPENDENCY,
        validator.DEPENDENCY_CYCLE,
        validator.VERIFIED_WITHOUT_EVIDENCE,
    }
    assert len(report.messages()) == len(report.errors)


def test_issue_str_is_its_message():
    report = validate_graph(graph(tasks=[task("t1", node_id="ghost")]))
    assert str(report.errors[0]) == report.errors[0].message