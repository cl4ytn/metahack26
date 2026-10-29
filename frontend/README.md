# GraphPilot frontend

Run `npm install`, then `npm run dev` with the API server on port 8000. Vite proxies `/api` to that server. Run `npm run build`, `npm run lint`, and `npm test` to verify changes.

The UI starts with a labelled, unverified sample until a server graph loads. It never substitutes successful API responses for connection or HTTP failures. Fixture-generated graphs remain labelled as fixed examples. The server owns approval, scheduling, verification and reset state. Save edits before running checks; approval saves the displayed graph and sends its returned revision as a precondition.

Verification requires a real JSON command argument array and server project directory. Results describe the supplied subprocess command; a zero exit code does not establish that every acceptance criterion has adequate test coverage. Evidence displays command output, revision provenance, simulation flags, execution records and diffs when the server provides them.

The graph supports pointer dragging and keyboard arrow movement. Drag previews remain inside the canvas and commit once when released. Native modal dialogs provide focus containment and Escape dismissal. Task evidence opens as a full-width view; the graph task board starts collapsed.

Styling is self-contained CSS, including responsive layouts and visible keyboard focus. Dependency installation was unavailable in the restricted editing environment, so Tailwind is not required. Full graph export uses JSON syntax, which is a valid YAML 1.2 subset, with standard JSON escaping and no omitted evidence fields.
