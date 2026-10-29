# GraphPilot use cases

This local prototype demonstrates workflows using one fixed Bookmarks Service graph. It does not generate new architectures or implement code.

| Workflow | Current behavior | Human responsibility |
| --- | --- | --- |
| Architecture review | Inspect and edit nodes, edges and task criteria; validate and approve a revision | Judge whether the design matches the requirement |
| Dependency planning | Calculate readiness from verified prerequisites and show downstream impact | Keep dependencies accurate |
| Test review | Run a supplied test command in a selected existing directory and inspect output | Write relevant tests and review coverage |
| Failure recovery | Block dependants after failure and recalculate after a successful retry | Repair the actual project code |
| Revision review | Clear approval and current evidence after semantic edits | Review and approve the new revision |

Potential future integrations include model-backed decomposition, coding-agent execution, repository snapshots and isolated runners. These are not implemented. Command results are local execution records, not universal proof of correctness, security or production readiness.
