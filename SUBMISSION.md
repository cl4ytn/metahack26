# GraphPilot submission

GraphPilot explores a graph-first review workflow: architecture dependencies, explicit human approval, task scheduling, dependency impact, and inspectable local test-command results.

## Implemented

- A React architecture canvas, task pipeline and evidence viewer.
- A fixed Bookmarks Service decomposition fixture, labeled in API provenance and UI.
- Schema and graph validation, including references and dependency cycles.
- Saved graph revisions with approval invalidation on semantic edits.
- Real subprocess commands with captured output, timeouts and exit outcomes.
- Prerequisite gating, downstream blocking, recovery and reset invalidation.
- Atomic YAML persistence for the local single-process workflow.

## Scope and limitations

No model API is called. No coding agent writes project code. The adapter is a fixture, not arbitrary requirement decomposition. Submitted diffs are claims. Verification records bind command and working directory to a graph revision, but do not snapshot the repository or prove acceptance-criteria coverage. Exit zero alone cannot establish correctness. The local command runner is not sandboxed; there is no authentication, durable multi-user transaction system or tamper-proof audit log.

See README.md for setup and tests and DEMO_SCRIPT.md for an honest end-to-end demonstration using actual failing and passing project tests.
