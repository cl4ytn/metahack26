"""Tests for services/test_runner.py.

Only the runner's own responsibility is tested: subprocess handling, outcome
mapping and evidence capture. Nothing here depends on the validator, scheduler
or coding agent, and no message wording from other modules is asserted.
"""

import os
import sys
import time
from pathlib import Path

import pytest

from backend.app.models.graph import VerificationOutcome, VerificationResult
from backend.app.services.test_runner import is_pytest_command, run_verification

PY = sys.executable


def run(command, cwd, **kwargs):
    return run_verification(
        command,
        verification_id="v1",
        task_id="t1",
        execution_id="e1",
        cwd=cwd,
        **kwargs,
    )


def py(code: str) -> list[str]:
    return [PY, "-c", code]


def run_inner_pytest(tmp_path: Path, source: str, *extra: str):
    (tmp_path / "test_inner.py").write_text(source)
    return run(
        [PY, "-m", "pytest", "-p", "no:cacheprovider", "-q", *extra],
        tmp_path,
        timeout_seconds=60,
    )


# ---------------------------------------------------------------- outcomes


def test_exit_zero_is_passed(tmp_path):
    result = run(py("print('hello')"), tmp_path)
    assert isinstance(result, VerificationResult)
    assert result.outcome == VerificationOutcome.PASSED
    assert result.passed is True
    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_nonzero_exit_is_failed_and_keeps_exit_code(tmp_path):
    result = run(py("import sys; sys.exit(3)"), tmp_path)
    assert result.outcome == VerificationOutcome.FAILED
    assert result.passed is False
    assert result.exit_code == 3


def test_non_pytest_command_never_maps_to_infrastructure_error(tmp_path):
    # Exit 5 is only special for pytest commands.
    result = run(py("import sys; sys.exit(5)"), tmp_path)
    assert result.outcome == VerificationOutcome.FAILED


def test_stderr_is_captured_separately(tmp_path):
    result = run(
        py("import sys; print('to-out'); print('to-err', file=sys.stderr); sys.exit(1)"),
        tmp_path,
    )
    assert "to-out" in result.stdout and "to-err" not in result.stdout
    assert "to-err" in result.stderr and "to-out" not in result.stderr


def test_evidence_fields_are_populated(tmp_path):
    result = run(py("pass"), tmp_path)
    assert (result.id, result.task_id, result.execution_id) == ("v1", "t1", "e1")
    assert "-c" in result.command
    assert result.finished_at is not None
    assert result.finished_at >= result.started_at


# ----------------------------------------------------------------- timeout


def test_timeout_maps_to_timed_out_and_returns_promptly(tmp_path):
    began = time.monotonic()
    result = run(py("import time; time.sleep(30)"), tmp_path, timeout_seconds=1.0)
    assert result.outcome == VerificationOutcome.TIMED_OUT
    assert result.passed is False
    assert result.exit_code is None
    assert time.monotonic() - began < 15


def test_timeout_keeps_partial_output(tmp_path):
    result = run(
        py("import time; print('partial-out', flush=True); time.sleep(30)"),
        tmp_path,
        timeout_seconds=1.5,
    )
    assert result.outcome == VerificationOutcome.TIMED_OUT
    assert "partial-out" in result.stdout


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")
def test_timeout_kills_grandchildren(tmp_path):
    marker = tmp_path / "marker.txt"
    (tmp_path / "child.py").write_text(
        "import sys, time, pathlib\n"
        "time.sleep(2)\n"
        "pathlib.Path(sys.argv[1]).write_text('survived')\n"
    )
    (tmp_path / "parent.py").write_text(
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, 'child.py', sys.argv[1]])\n"
        "time.sleep(30)\n"
    )
    result = run(
        [PY, "parent.py", str(marker)], tmp_path, timeout_seconds=1.0
    )
    assert result.outcome == VerificationOutcome.TIMED_OUT
    time.sleep(3.5)
    assert not marker.exists()


# ---------------------------------------------------- infrastructure errors


def test_missing_executable_is_infrastructure_error(tmp_path):
    result = run(["definitely-not-a-real-executable-xyz"], tmp_path)
    assert result.outcome == VerificationOutcome.INFRASTRUCTURE_ERROR
    assert result.exit_code is None
    assert result.stderr != ""


def test_missing_cwd_is_infrastructure_error(tmp_path):
    result = run(py("pass"), tmp_path / "does-not-exist")
    assert result.outcome == VerificationOutcome.INFRASTRUCTURE_ERROR
    assert result.exit_code is None
    assert result.passed is False


# ------------------------------------------------------------ pytest-aware


def test_is_pytest_command_detection():
    assert is_pytest_command(["pytest", "-v"])
    assert is_pytest_command(["/usr/bin/py.test"])
    assert is_pytest_command(["python", "-m", "pytest", "tests"])
    assert is_pytest_command([PY, "-m", "pytest"])
    assert not is_pytest_command(["python", "-c", "pass"])
    assert not is_pytest_command(["python", "-m", "unittest"])
    assert not is_pytest_command(["echo", "pytest"])
    assert not is_pytest_command([])


def test_pytest_pass(tmp_path):
    result = run_inner_pytest(tmp_path, "def test_ok():\n    assert True\n")
    assert result.outcome == VerificationOutcome.PASSED
    assert result.exit_code == 0


def test_pytest_failing_test_is_failed(tmp_path):
    result = run_inner_pytest(tmp_path, "def test_bad():\n    assert False\n")
    assert result.outcome == VerificationOutcome.FAILED
    assert result.exit_code == 1


def test_pytest_no_tests_collected_is_infrastructure_error(tmp_path):
    result = run_inner_pytest(tmp_path, "x = 1\n")
    assert result.exit_code == 5
    assert result.outcome == VerificationOutcome.INFRASTRUCTURE_ERROR
    assert result.passed is False


def test_pytest_usage_error_is_infrastructure_error(tmp_path):
    result = run_inner_pytest(
        tmp_path, "def test_ok():\n    pass\n", "--no-such-option-xyz"
    )
    assert result.exit_code == 4
    assert result.outcome == VerificationOutcome.INFRASTRUCTURE_ERROR


def test_pytest_collection_error_in_code_under_test_is_failed(tmp_path):
    result = run_inner_pytest(tmp_path, "import module_that_does_not_exist\n")
    assert result.exit_code == 2
    assert result.outcome == VerificationOutcome.FAILED


# --------------------------------------------------------- output handling


def test_output_is_truncated_keeping_the_tail(tmp_path):
    result = run(
        py("print('a' * 50000); print('FINAL-LINE')"),
        tmp_path,
        max_output_chars=1000,
    )
    assert result.outcome == VerificationOutcome.PASSED
    assert len(result.stdout) < 2000
    assert result.stdout.rstrip().endswith("FINAL-LINE")
    assert "truncated" in result.stdout


def test_short_output_is_not_marked_truncated(tmp_path):
    result = run(py("print('short')"), tmp_path, max_output_chars=1000)
    assert result.stdout.strip() == "short"


def test_non_utf8_output_does_not_crash(tmp_path):
    result = run(
        py("import sys; sys.stdout.buffer.write(b'ok \\xff\\xfe end')"), tmp_path
    )
    assert result.outcome == VerificationOutcome.PASSED
    assert "ok" in result.stdout and "end" in result.stdout


# --------------------------------------------------- process-level hygiene


def test_stdin_is_closed(tmp_path):
    result = run(
        py("import sys; sys.exit(0 if sys.stdin.read() == '' else 1)"),
        tmp_path,
        timeout_seconds=10,
    )
    assert result.outcome == VerificationOutcome.PASSED


def test_no_shell_interpretation(tmp_path):
    payload = "a; echo injected && $HOME"
    result = run(py("import sys; print(sys.argv[1])") + [payload], tmp_path)
    assert result.stdout.strip() == payload


def test_cwd_is_honoured(tmp_path):
    result = run(py("import os; print(os.getcwd())"), tmp_path)
    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()


# -------------------------------------------------------------- caller bugs


def test_empty_command_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        run([], tmp_path)


def test_non_string_command_part_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        run([PY, 5], tmp_path)  # type: ignore[list-item]


@pytest.mark.parametrize("bad", [0, -1])
def test_non_positive_timeout_raises_value_error(tmp_path, bad):
    with pytest.raises(ValueError):
        run(py("pass"), tmp_path, timeout_seconds=bad)


@pytest.mark.parametrize("bad", [0, -5])
def test_non_positive_output_cap_raises_value_error(tmp_path, bad):
    with pytest.raises(ValueError):
        run(py("pass"), tmp_path, max_output_chars=bad)