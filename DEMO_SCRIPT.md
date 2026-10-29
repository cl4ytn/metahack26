# GraphPilot demo

Describe this as a local workflow prototype. The decomposition is a fixed Bookmarks Service fixture, with no model call and no coding agent.

1. **Load and inspect**: Start the backend and frontend using `README.md`. Load the fixture and note the explicit fixture label. Different prompts record different requirement text but retain the same architecture.
2. **Review & approve revision**: Review a node, its dependencies and acceptance criteria. Edit and save a description, then approve the exact saved revision. Show that another semantic edit returns the graph to draft.
3. **Inspect impact**: Use the impact view to inspect transitive dependants. This is a dependency estimate, not a source-code analysis.
4. **Demonstrate real failure & DAG lockdown (Bundled `sample_project`)**:
   - Select the root database task (`task-db-schema`).
   - Notice the default project directory is set to `sample_project` and preset command `python -m unittest test_db_schema.py`.
   - Click **Run configured checks**.
   - Show the real Python `unittest` failure output (`AssertionError: missing index on url_hash`).
   - Switch to the **Graph** tab: notice `Bookmarks Database` shows `🔴 Failed 1` and downstream nodes immediately turn amber with `⚠️ Blocked`.
5. **Repair implementation & unlock DAG**:
   - In `sample_project/db_schema.py`, switch to the repaired schema (uncommenting `CREATE INDEX idx_bookmarks_url_hash`).
   - Rerun `python -m unittest test_db_schema.py`.
   - The test exits `0`. `task-db-schema` marks `Verified 1/1`.
   - Also run `python -m unittest test_slug.py` for `task-slug`.
   - Show that the downstream `Link Service` automatically recalculates to `🟡 Ready 1`!
6. **Reset & Invalidation**:
   - Reset the root task and show that dependent completion is invalidated and readiness is recomputed.

Do not present a simulation or a command that simply prints success as implementation evidence. A command pass says only that the selected command exited zero; test coverage remains a human review responsibility. The runner is a subprocess, not a security sandbox.
