"""Tests for app.storage.yaml_store.

ASSUMPTIONS about the real graph.py (fix only the helpers below if wrong):
  “ArchitectureGraph requires only project_name; every other field has a default (requirement defaults to \"\").”
  * Node has id/type/name, Edge has id/source/target/type,
    Task has id/node_id/title (status defaults to pending).
    Executions and verifications are NOT used here because their required
    fields were not provided.
"""

import pytest
import yaml
from pydantic import ValidationError

from backend.app.models.graph import ArchitectureGraph
from backend.app.services.validator import validate_graph
from backend.app.storage import yaml_store
from backend.app.storage.yaml_store import (
    GraphFileNotFoundError,
    GraphParseError,
    GraphSchemaError,
    GraphStoreError,
    InvalidGraphError,
    load_graph,
    save_graph,
)


# --------------------------------------------------------------------------
# Helpers (the only place that knows model field names beyond the contract)
# --------------------------------------------------------------------------
def _graph(**fields) -> ArchitectureGraph:
    data = {"project_name": "demo", "requirement": "Build a todo app"}
    data.update(fields)
    return ArchitectureGraph.model_validate(data)


def _rich_graph() -> ArchitectureGraph:
    return _graph(
        status="approved",
        approved_at="2026-10-29T10:00:00Z",
        nodes=[
            {"id": "n1", "type": "service", "name": "API"},
            {"id": "n2", "type": "database", "name": "DB"},
        ],
        edges=[{"id": "e1", "source": "n1", "target": "n2", "type": "reads_from"}],
        tasks=[
            {"id": "t1", "node_id": "n2", "title": "Create schema"},
            {"id": "t2", "node_id": "n1", "title": "Implement API", "depends_on": ["t1"]},
        ],
    )


def _invalid_graph() -> ArchitectureGraph:
    """Loads fine (models don't enforce uniqueness) but fails validation."""
    return _graph(
        nodes=[
            {"id": "n1", "type": "service", "name": "A"},
            {"id": "n1", "type": "service", "name": "B"},
        ]
    )


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------
def test_minimal_graph_round_trips(tmp_path):
    path = tmp_path / "architecture.yaml"
    g = _graph()
    save_graph(g, path)
    assert load_graph(path) == g


def test_rich_graph_round_trips(tmp_path):
    path = tmp_path / "architecture.yaml"
    g = _rich_graph()
    save_graph(g, path)
    assert load_graph(path) == g


def test_unicode_round_trips(tmp_path):
    path = tmp_path / "architecture.yaml"
    g = _graph(project_name="Café 日本", requirement="Zażółć gęślą jaźń")
    save_graph(g, path)
    assert load_graph(path) == g


def test_save_then_load_then_save_is_byte_identical(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    save_graph(_rich_graph(), a)
    save_graph(load_graph(a), b)
    assert a.read_bytes() == b.read_bytes()


def test_keys_are_written_in_model_order_not_sorted(tmp_path):
    path = tmp_path / "architecture.yaml"
    g = _rich_graph()
    save_graph(g, path)
    assert list(yaml.safe_load(path.read_text("utf-8"))) == list(g.model_dump(mode="json"))


def test_accepts_str_paths_and_creates_parent_directories(tmp_path):
    path = str(tmp_path / "deep" / "er" / "architecture.yaml")
    g = _graph()
    save_graph(g, path)
    assert load_graph(path) == g


# --------------------------------------------------------------------------
# load_graph failures are specific and never return a default graph
# --------------------------------------------------------------------------
def test_missing_file_raises_not_found(tmp_path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(GraphFileNotFoundError) as exc:
        load_graph(missing)
    assert exc.value.path == missing
    assert isinstance(exc.value, GraphStoreError)


@pytest.mark.parametrize(
    "content",
    ["key: [unclosed", "a: b: c: [", "", "   \n", "- a\n- b\n", "just a string\n", "42\n"],
    ids=["unclosed-flow", "bad-nesting", "empty", "whitespace", "list", "scalar-str", "scalar-int"],
)
def test_unparseable_or_non_mapping_raises_parse_error(tmp_path, content):
    path = tmp_path / "architecture.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(GraphParseError) as exc:
        load_graph(path)
    assert exc.value.path == path


def test_non_utf8_file_raises_parse_error(tmp_path):
    path = tmp_path / "architecture.yaml"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(GraphParseError):
        load_graph(path)


def test_unknown_field_raises_schema_error_with_original_cause(tmp_path):
    path = tmp_path / "architecture.yaml"
    data = _graph().model_dump(mode="json")
    data["bogus"] = 1
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(GraphSchemaError) as exc:
        load_graph(path)
    assert isinstance(exc.value.error, ValidationError)
    assert isinstance(exc.value.__cause__, ValidationError)
    assert "bogus" in str(exc.value)


def test_bad_enum_value_raises_schema_error(tmp_path):
    path = tmp_path / "architecture.yaml"
    data = _graph().model_dump(mode="json")
    data["status"] = "weird"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises(GraphSchemaError):
        load_graph(path)


def test_missing_required_field_raises_schema_error(tmp_path):
    path = tmp_path / "architecture.yaml"
    path.write_text("requirement: build a todo app\n", encoding="utf-8")  # no project_name
    with pytest.raises(GraphSchemaError) as exc:
        load_graph(path)
    assert "project_name" in str(exc.value)


def test_load_does_not_validate_semantics_so_invalid_files_stay_inspectable(tmp_path):
    path = tmp_path / "architecture.yaml"
    g = _invalid_graph()
    # Written directly, bypassing save_graph's guard.
    path.write_text(yaml.safe_dump(g.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    loaded = load_graph(path)
    assert loaded == g
    assert not validate_graph(loaded).is_valid


# --------------------------------------------------------------------------
# save_graph refuses invalid graphs
# --------------------------------------------------------------------------
def test_invalid_graph_is_refused_and_nothing_is_written(tmp_path):
    path = tmp_path / "architecture.yaml"
    with pytest.raises(InvalidGraphError) as exc:
        save_graph(_invalid_graph(), path)
    report = exc.value.report
    assert not report.is_valid
    assert any(i.code == "duplicate_id" for i in report.errors)
    for message in report.messages():
        assert message in str(exc.value)
    assert list(tmp_path.iterdir()) == []  # no file, no temp leftovers


def test_invalid_graph_leaves_existing_file_untouched(tmp_path):
    path = tmp_path / "architecture.yaml"
    save_graph(_graph(project_name="good"), path)
    before = path.read_bytes()
    with pytest.raises(InvalidGraphError):
        save_graph(_invalid_graph(), path)
    assert path.read_bytes() == before


def test_save_overwrites_existing_valid_file(tmp_path):
    path = tmp_path / "architecture.yaml"
    save_graph(_graph(project_name="old"), path)
    new = _rich_graph()
    save_graph(new, path)
    assert load_graph(path) == new


# --------------------------------------------------------------------------
# Atomicity
# --------------------------------------------------------------------------
def test_successful_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "architecture.yaml"
    save_graph(_rich_graph(), path)
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replace_keeps_original_and_removes_temp(tmp_path, monkeypatch):
    path = tmp_path / "architecture.yaml"
    save_graph(_graph(project_name="old"), path)
    before = path.read_bytes()

    def boom(src, dst):
        raise OSError("disk on fire")

    monkeypatch.setattr(yaml_store.os, "replace", boom)
    with pytest.raises(OSError, match="disk on fire"):
        save_graph(_rich_graph(), path)

    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_failed_first_write_leaves_no_file(tmp_path, monkeypatch):
    path = tmp_path / "architecture.yaml"

    def boom(src, dst):
        raise OSError("disk on fire")

    monkeypatch.setattr(yaml_store.os, "replace", boom)
    with pytest.raises(OSError):
        save_graph(_graph(), path)
    assert list(tmp_path.iterdir()) == []