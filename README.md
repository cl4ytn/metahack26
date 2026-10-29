# GraphPilot

GraphPilot is a local architecture and task-verification prototype. It displays a dependency graph, validates references and cycles, records approval for the current revision, estimates downstream impact, and runs user-supplied test commands.

The decomposition adapter returns a **fixed Bookmarks Service fixture**. The entered requirement is recorded but does not generate a new architecture. No model API or coding agent is connected, and this application does not implement the displayed tasks. Execution diffs and changed-file lists are user-supplied claims; they are not generated or independently inspected.

## Run locally

From the repository root, with Python 3.11+ and uv installed:

```powershell
uv run --with fastapi --with uvicorn --with pydantic --with pyyaml uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. API documentation is at http://localhost:8000/docs.

## Workflow

1. Load the labeled fixture and review or edit the graph.
2. Save edits and approve the resulting revision. Semantic edits clear approval and current task evidence.
3. Select a task whose prerequisites are verified. The interface accepts natural command syntax (e.g. `python -m unittest test_db_schema.py`) as well as JSON arrays (`["python", "-m", "unittest"]`). Use the bundled zero-dependency `sample_project` or supply an existing directory. Quick-fill preset chips are provided per task.
4. Inspect the actual command, working directory, graph revision, output, exit code, and timestamps. Nodes on the canvas visually display live task status badges (`Verified`, `Ready`, `Blocked`, `Failed`). A missing command is an error; no successful test output is fabricated.
5. A nonzero result fails the task and blocks downstream tasks. A successful retry recalculates readiness. Resetting a prerequisite invalidates its downstream completion states.

`verified` means only that the recorded command exited zero for that graph revision. Users must review whether the selected tests cover the acceptance criteria. Graph revision binding does not fingerprint project files or prove that files remain unchanged after a run. A command that does no meaningful testing can still exit zero.

State is saved to `architecture.yaml` through atomic file replacement. This is a single-process local prototype, without authentication, multi-user transactions, tamper resistance, repository snapshots, or an execution sandbox. Commands run with the backend user's permissions. Keep the API local and run trusted commands.

## Tests

```powershell
uv run --with fastapi --with pydantic --with pyyaml --with httpx --with pytest python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

Backend tests include real subprocess execution against temporary project files, failure and recovery, approval invalidation, blocked prerequisite refusal, direct status override refusal, and reset behavior.
