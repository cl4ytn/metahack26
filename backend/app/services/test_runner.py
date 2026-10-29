"""Independent test runner: the only legitimate producer of verification evidence.

Runs a caller-supplied test command (an argv list, never a shell string) in a
subprocess with a timeout, captures its output and exit code, maps the result
to a ``VerificationOutcome`` and returns a ``VerificationResult``.

It does NOT call the coding agent, persist the graph, or change task status.
Applying the result (``implemented -> verifying -> verified`` or ``failed``)
is the caller's job. A ``passed`` outcome here means the command exited 0,
nothing else.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from backend.app.models.graph import VerificationOutcome, VerificationResult

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_OUTPUT_CHARS = 20_000

# After killing a timed-out process, how long to wait for its pipes to drain.
_DRAIN_GRACE_SECONDS = 5.0

# pytest exit codes that mean "the tests could not be run / judged", not
# "the tests ran and failed":
#   3 internal error, 4 command-line usage error, 5 no tests collected.
# Exit 5 matters most: an empty test selection must never be read as a pass
# (it is nonzero anyway) nor as a code failure.
# Exit 2 (interrupted, which includes collection errors such as an import
# error in the code under test) deliberately stays `failed`: a broken
# implementation is the code's fault, not the infrastructure's.
_PYTEST_INFRASTRUCTURE_EXIT_CODES = frozenset({3, 4, 5})

_TRUNCATION_MARKER = "[... output truncated: {dropped} earlier characters omitted ...]\n"


def is_pytest_command(command: Sequence[str]) -> bool:
    """True for ``pytest ...``, ``py.test ...`` and ``python -m pytest ...``."""
    if not command:
        return False
    first = os.path.basename(command[0]).lower()
    if first.endswith(".exe"):
        first = first[:-4]
    if first in {"pytest", "py.test"}:
        return True
    return (
        first.startswith("python")
        and len(command) >= 3
        and command[1] == "-m"
        and command[2] == "pytest"
    )


def _classify_exit_code(command: Sequence[str], exit_code: int) -> VerificationOutcome:
    if exit_code == 0:
        return VerificationOutcome.PASSED
    if is_pytest_command(command) and exit_code in _PYTEST_INFRASTRUCTURE_EXIT_CODES:
        return VerificationOutcome.INFRASTRUCTURE_ERROR
    return VerificationOutcome.FAILED


def _as_text(value: str | bytes | None) -> str:
    """TimeoutExpired may carry bytes even when the process ran in text mode."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _truncate(text: str, limit: int) -> str:
    """Keep the tail (pytest puts its summary last) and say what was dropped."""
    if len(text) <= limit:
        return text
    dropped = len(text) - limit
    return _TRUNCATION_MARKER.format(dropped=dropped) + text[-limit:]


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill the process and, on POSIX, its whole process group."""
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            proc.kill()
    else:  # pragma: no cover - Windows: only the direct child is killed
        proc.kill()


def run_verification(
    command: Sequence[str],
    *,
    verification_id: str,
    task_id: str,
    execution_id: str,
    cwd: str | os.PathLike[str],
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
) -> VerificationResult:
    """Run ``command`` and return the evidence record. Never raises for a
    test failure, a timeout or a launch failure; those are outcomes.

    Raises:
        ValueError: ``command`` is empty or a limit is not positive
            (caller bugs, not test results).
        pydantic.ValidationError: an id does not match the graph's id rules.

    The command is an argv list and is never passed through a shell.
    stdin is closed so a test that prompts cannot hang the run.
    """
    argv = list(command)
    if not argv or not all(isinstance(part, str) for part in argv):
        raise ValueError("command must be a non-empty sequence of strings")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_output_chars <= 0:
        raise ValueError("max_output_chars must be positive")

    command_text = shlex.join(argv)
    started_at = datetime.now(timezone.utc)

    def build(
        outcome: VerificationOutcome,
        exit_code: int | None,
        stdout: str,
        stderr: str,
    ) -> VerificationResult:
        return VerificationResult(
            id=verification_id,
            task_id=task_id,
            execution_id=execution_id,
            command=command_text,
            outcome=outcome,
            exit_code=exit_code,
            stdout=_truncate(stdout, max_output_chars),
            stderr=_truncate(stderr, max_output_chars),
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )

    try:
        proc = subprocess.Popen(
            argv,
            cwd=Path(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=(os.name == "posix"),
        )
    except OSError as exc:  # missing executable, bad cwd, permissions
        return build(
            VerificationOutcome.INFRASTRUCTURE_ERROR,
            None,
            "",
            f"{type(exc).__name__}: {exc}",
        )

    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            try:
                stdout, stderr = proc.communicate(timeout=_DRAIN_GRACE_SECONDS)
            except subprocess.TimeoutExpired as drain:
                stdout, stderr = _as_text(drain.stdout), _as_text(drain.stderr)
            return build(
                VerificationOutcome.TIMED_OUT, None, _as_text(stdout), _as_text(stderr)
            )
    except BaseException:
        _kill_process_tree(proc)
        raise

    exit_code = proc.returncode
    return build(_classify_exit_code(argv, exit_code), exit_code, stdout, stderr)