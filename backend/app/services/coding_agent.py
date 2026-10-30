"""Coding agent adapter: narrow Protocol + scripted fixture (stand-in).

Stand-in policy: this module defines the interface only. The fixture is a
scripted replay, never a live model call. It returns a CLAIMED result;
verification is done by the real test_runner, never by the agent.

Real adapters can replace FixtureCodingAgent without touching other modules.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from backend.app.models.graph import ArchitectureGraph, Task

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskContext:
    """Everything the agent sees for one task.

    `graph` is a deep-copied read-only snapshot; the adapter must not rely
    on mutating it and must not assume it is the live graph.
    `workdir` is the directory the agent may write under.
    """
    task: Task
    graph: ArchitectureGraph
    workdir: Path


@dataclass(frozen=True)
class AgentResult:
    """What an agent returns. Every field here is the agent's CLAIM.

    Nothing in this record may be treated as grounds for `verified`.
    """
    agent_name: str
    changed_files: list[str] = field(default_factory=list)
    diff: str = ""
    agent_reported_success: bool | None = None
    external_run_id: str | None = None


@runtime_checkable
class CodingAgentAdapter(Protocol):
    def name(self) -> str: ...
    def is_fixture(self) -> bool: ...
    def execute_task(self, context: TaskContext) -> AgentResult: ...


class FixtureCodingAgent:
    """Scripted stand-in. Applies a fixed edit; never a live model call.

    Writes a scratch file under `<workdir>/src/<task_id>.py` and reports it
    as a claimed change. Real code generation is out of scope for the fixture.
    """

    def name(self) -> str:
        return "coding-agent-fixture-replay"

    def is_fixture(self) -> bool:
        return True

    def execute_task(self, context: TaskContext) -> AgentResult:
        task = context.task
        target = context.workdir / "src" / f"{task.id}.py"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                f"# GraphPilot fixture replay for task {task.id}\n"
                f"def main():\n"
                f"    return True\n",
                encoding="utf-8",
            )
            logger.info(
                "coding-agent fixture applied scripted edit: %s "
                "(task=%s, fixture/replayed, no model call)",
                target, task.id,
            )
            write_ok = True
        except OSError as exc:
            logger.warning(
                "coding-agent fixture could not write %s: %s "
                "(task=%s, fixture/replayed, no model call)",
                target, exc, task.id,
            )
            write_ok = False
        return AgentResult(
            agent_name=self.name(),
            changed_files=[f"src/{task.id}.py"],
            diff=(
                f"--- /dev/null\n"
                f"+++ b/src/{task.id}.py\n"
                f"+# GraphPilot fixture replay for task {task.id}\n"
                f"+def main():\n"
                f"+    return True\n"
            ),
            agent_reported_success=write_ok,
            external_run_id=None,
        )