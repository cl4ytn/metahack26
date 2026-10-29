"""Read and write ``architecture.yaml``.

This module owns persistence only. It does not own graph semantics (the
validator does), scheduling, or model calls.

Contract:
    load_graph(path) -> ArchitectureGraph
        Parses and schema-checks the file. It deliberately does NOT run
        ``validate_graph``: a file with duplicate IDs, dangling references or
        cycles still loads so it can be inspected. Callers validate.

    save_graph(graph, path) -> None
        Runs ``validate_graph`` first and refuses to write an invalid graph.
        The write is atomic (temp file in the same directory, then
        ``os.replace``), so a crash never leaves a half-written file.

Nothing here repairs, defaults or swallows a failure.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError

from backend.app.models.graph import ArchitectureGraph
from backend.app.services.validator import ValidationReport, validate_graph

PathLike = str | os.PathLike[str]


class GraphStoreError(Exception):
    """Base class for every failure raised by this module."""


class GraphFileNotFoundError(GraphStoreError):
    """The architecture file does not exist."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Architecture file not found: {path}")


class GraphParseError(GraphStoreError):
    """The file is not readable YAML, or its top level is not a mapping."""

    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Cannot parse {path}: {detail}")


class GraphSchemaError(GraphStoreError):
    """The YAML parsed, but does not match the ``ArchitectureGraph`` schema."""

    def __init__(self, path: Path, error: ValidationError) -> None:
        self.path = path
        self.error = error
        super().__init__(
            f"{path} does not match the architecture graph schema "
            f"({error.error_count()} error(s)):\n{error}"
        )


class InvalidGraphError(GraphStoreError):
    """``save_graph`` refused to write a graph that fails validation."""

    def __init__(self, path: Path, report: ValidationReport) -> None:
        self.path = path
        self.report = report
        details = "\n".join(f"- {m}" for m in report.messages())
        super().__init__(
            f"Refusing to write an invalid graph to {path}:\n{details}"
        )


def load_graph(path: PathLike) -> ArchitectureGraph:
    """Load ``path`` into an ``ArchitectureGraph``.

    Raises:
        GraphFileNotFoundError: the file does not exist.
        GraphParseError: not valid UTF-8 / YAML, or not a top-level mapping
            (an empty file counts as "not a mapping").
        GraphSchemaError: Pydantic rejected the data. ``.error`` holds the
            original ``pydantic.ValidationError``.
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise GraphFileNotFoundError(p) from exc
    except UnicodeDecodeError as exc:
        raise GraphParseError(p, f"file is not valid UTF-8 ({exc})") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise GraphParseError(p, str(exc)) from exc

    if not isinstance(data, dict):
        found = "nothing (empty file)" if data is None else type(data).__name__
        raise GraphParseError(p, f"expected a mapping at the top level, found {found}")

    try:
        return ArchitectureGraph.model_validate(data)
    except ValidationError as exc:
        raise GraphSchemaError(p, exc) from exc


def save_graph(graph: ArchitectureGraph, path: PathLike) -> None:
    """Validate ``graph`` and atomically write it to ``path``.

    Raises:
        InvalidGraphError: validation failed; nothing was written and any
            existing file is untouched. ``.report`` has the ValidationReport.
        OSError: the filesystem refused the write; the original file (if any)
            is untouched and the temp file is removed.
    """
    p = Path(path)
    report = validate_graph(graph)
    if not report.is_valid:
        raise InvalidGraphError(p, report)

    # Serialize fully before touching the disk.
    text = yaml.safe_dump(
        graph.model_dump(mode="json"),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    _atomic_write_text(p, text)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; make it a normal file
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise