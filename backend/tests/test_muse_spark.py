"""Tests for app.services.muse_spark (adapter contract + replayed fixture).

These tests cover this module's own responsibility: that the fixture satisfies
the Protocol, labels itself as a replay, and emits a draft graph. They assert
`validate_graph(...).is_valid` as a contract check on the fixture's output but
never assert on the validator's message wording.
"""

from __future__ import annotations

import logging

import pytest

from backend.app.models.graph import ArchitectureGraph, GraphStatus, TaskStatus
from backend.app.services.muse_spark import (
    FIXTURE_NAME,
    FixtureMuseSpark,
    MuseSparkAdapter,
)
from backend.app.services.validator import validate_graph


def _graph(requirement: str = "Build a small bookmarks service with a web UI."):
    return FixtureMuseSpark().generate_graph(requirement)


def test_fixture_satisfies_the_adapter_protocol():
    assert isinstance(FixtureMuseSpark(), MuseSparkAdapter)


def test_fixture_identifies_itself_as_a_replay():
    adapter = FixtureMuseSpark()
    assert adapter.name() == FIXTURE_NAME
    assert adapter.is_fixture() is True
    assert "fixture" in adapter.name().lower()
    assert "replay" in adapter.name().lower()


def test_generate_graph_returns_an_architecture_graph():
    assert isinstance(_graph(), ArchitectureGraph)


def test_fixture_graph_passes_the_real_validator():
    report = validate_graph(_graph())
    assert report.is_valid, report.messages()
    assert report.errors == []


def test_output_is_deterministic_for_the_same_requirement():
    assert _graph("same text") == _graph("same text")


def test_requirement_text_is_recorded_and_stripped():
    graph = _graph("  Build a bookmarks service.  ")
    assert graph.requirement == "Build a bookmarks service."


def test_fixture_graph_is_a_draft_and_not_approved():
    graph = _graph()
    assert graph.status == GraphStatus("draft")
    assert graph.approved_at is None


def test_fixture_graph_carries_no_evidence():
    graph = _graph()
    assert graph.executions == []
    assert graph.verifications == []
    for task in graph.tasks:
        assert task.status == TaskStatus("pending")
        assert task.execution_ids == []
        assert task.verification_ids == []


def test_every_reference_in_the_fixture_graph_resolves():
    graph = _graph()
    node_ids = {node.id for node in graph.nodes}
    task_ids = {task.id for task in graph.tasks}

    for edge in graph.edges:
        assert edge.source in node_ids
        assert edge.target in node_ids
    for task in graph.tasks:
        assert task.node_id in node_ids
        assert set(task.depends_on) <= task_ids


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_blank_requirement_is_rejected(blank):
    with pytest.raises(ValueError):
        FixtureMuseSpark().generate_graph(blank)


def test_calls_do_not_share_mutable_state():
    first = _graph()
    expected_tasks = len(first.tasks)
    assert expected_tasks > 0

    first.tasks.clear()
    first.nodes.clear()

    second = _graph()
    assert len(second.tasks) == expected_tasks
    assert len(second.nodes) > 0


def test_generate_graph_logs_that_the_output_is_replayed(caplog):
    with caplog.at_level(logging.INFO, logger="backend.app.services.muse_spark"):
        _graph()

    messages = " ".join(record.getMessage().lower() for record in caplog.records)
    assert "fixture" in messages
    assert "replay" in messages
    assert "no model call" in messages