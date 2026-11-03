// frontend/src/components/MusePanel.tsx
//
// VS Code Copilot-style right pane, renamed "Muse" for GraphPilot.
// Hosts the refine input, the approve action, and the refinement_history
// rendered as a chat-style audit log.
//
// Rules enforced here:
//   - refinement_history is an AUDIT LOG. Each RefinementTurn.instruction is
//     a historical user message; ids are historical. Nothing here resolves
//     turn ids against the current graph.
//   - is_fixture is shown verbatim on every render alongside the adapter
//     name, mirroring the badge on the graph view.
//   - No YAML, no validation logic, no fabrication of task execution.
//   - in implementation phase the panel states plainly that task-execution
//     results are not yet surfaced by the backend.
//
// Callback contract:
//   onRefine / onApprove MUST reject on failure. The panel awaits them:
//     - resolve  -> panel clears the instruction (refine) or relies on the
//                   parent flipping phase (approve)
//     - reject   -> panel keeps the instruction; the parent is expected to
//                   set the `error` prop with a human-readable message
//   The panel never inspects the exception value.

import { useState } from "react";
import type { CSSProperties } from "react";
import type {
  AdapterMetadata,
  ArchitectureGraph,
  RefinementTurn,
} from "../types";

// Mirrors App.tsx BusyKind. Duplicated deliberately to keep MusePanel free of
// an App import.
type BusyKind = null | "generate" | "refine" | "approve";

type PanelPhase = "design" | "implementation";

interface MusePanelProps {
  graph: ArchitectureGraph | null;
  adapter: AdapterMetadata | null;
  phase: PanelPhase;
  busy: BusyKind;
  error: string | null;
  onRefine: (instruction: string) => Promise<void>;
  onApprove: () => Promise<void>;
  onDismissError: () => void;
}

const SUGGESTIONS: string[] = [
  "add auth",
  "remove task-slug",
  "rename svc-links to svc-links-v2",
];

// ---------------------------------------------------------------------------
// Audit log turn
// ---------------------------------------------------------------------------

function Turn({
  turn,
  index,
}: {
  turn: RefinementTurn;
  index: number;
}) {
  const changes = [
    { label: "nodes added", values: turn.node_ids_added },
    { label: "nodes removed", values: turn.node_ids_removed },
    { label: "edges added", values: turn.edge_ids_added },
    { label: "edges removed", values: turn.edge_ids_removed },
    { label: "tasks added", values: turn.task_ids_added },
    { label: "tasks removed", values: turn.task_ids_removed },
  ].filter((c) => c.values.length > 0);

  return (
    <div style={turnWrapStyle}>
      <div style={userBubbleStyle}>{turn.instruction}</div>
      <div style={systemBubbleStyle}>
        <div style={systemLabelStyle}>Applied · turn {index + 1}</div>
        {changes.length === 0 ? (
          <div style={mutedTextStyle}>(no id changes recorded)</div>
        ) : (
          <ul style={changeListStyle}>
            {changes.map((c) => (
              <li key={c.label} style={changeItemStyle}>
                <span style={changeLabelStyle}>{c.label}:</span>{" "}
                <span style={changeValuesStyle}>{c.values.join(", ")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MusePanel({
  graph,
  adapter,
  phase,
  busy,
  error,
  onRefine,
  onApprove,
  onDismissError,
}: MusePanelProps) {
  const [instruction, setInstruction] = useState("");

  const designPhase = phase === "design";
  const idle = busy === null;
  const canRefine =
    !!graph && designPhase && idle && instruction.trim().length > 0;
  const canApprove = !!graph && designPhase && idle;

  const submitRefine = async () => {
    if (!canRefine) return;
    const text = instruction.trim();
    try {
      await onRefine(text);
      setInstruction("");
    } catch {
      // Parent sets `error`. Keep instruction so the user can retry.
    }
  };

  const submitApprove = async () => {
    if (!canApprove) return;
    try {
      await onApprove();
    } catch {
      // Parent sets `error`.
    }
  };

  const history = graph?.refinement_history ?? [];

  return (
    <div style={containerStyle}>
      <header style={headerStyle}>
        <span>Muse</span>
        {graph && (
          <span style={graphMetaStyle}>
            {graph.schema_version} · {graph.status}
          </span>
        )}
      </header>

      {adapter && (
        <div style={adapterStripStyle}>
          <span style={adapterNameStyle} title="Adapter">
            {adapter.name}
          </span>
          <span style={adapter.is_fixture ? fixturePillStyle : livePillStyle}>
            {adapter.is_fixture ? "FIXTURE — replayed, no model call" : "LIVE"}
          </span>
        </div>
      )}

      {error && (
        <div style={errorStyle} role="alert">
          <div style={{ flex: 1 }}>{error}</div>
          <button
            type="button"
            onClick={onDismissError}
            style={dismissButtonStyle}
          >
            Dismiss
          </button>
        </div>
      )}

      {phase === "implementation" && (
        <div style={phaseBannerStyle}>
          <div style={{ fontWeight: 600, marginBottom: 2 }}>Approved</div>
          This graph is now the reference for implementation. Task-execution
          results are not yet surfaced by the backend.
        </div>
      )}

      <div style={auditHeadingStyle}>
        Refinement history (audit log — not current entities)
      </div>

      <div style={historyScrollStyle}>
        {!graph ? (
          <p style={emptyTextStyle}>
            Generate an architecture to start a conversation.
          </p>
        ) : history.length === 0 ? (
          <p style={emptyTextStyle}>No refinement turns recorded.</p>
        ) : (
          history.map((t, i) => <Turn key={i} turn={t} index={i} />)
        )}
      </div>

      {designPhase && graph && idle && instruction.trim().length === 0 && (
        <div style={suggestionsStyle}>
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setInstruction(s)}
              style={chipStyle}
              title={`Use "${s}"`}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div style={inputRowStyle}>
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submitRefine();
            }
          }}
          placeholder={
            designPhase
              ? "Refine instruction…"
              : "Graph approved — refine disabled"
          }
          disabled={!graph || !designPhase || !idle}
          style={inputStyle}
          spellCheck={false}
          autoComplete="off"
        />
        <button
          type="button"
          onClick={() => void submitRefine()}
          disabled={!canRefine}
          style={canRefine ? primaryButtonStyle : primaryButtonDisabledStyle}
        >
          {busy === "refine" ? "Refining…" : "Refine"}
        </button>
      </div>

      <div style={dividerStyle} />

      <div style={approveRowStyle}>
        <button
          type="button"
          onClick={() => void submitApprove()}
          disabled={!canApprove}
          style={
            canApprove
              ? approveButtonStyle
              : approveButtonDisabledStyle
          }
        >
          {busy === "approve"
            ? "Approving…"
            : phase === "implementation"
            ? "Approved"
            : "Approve & persist"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles (VS Code dark)
// ---------------------------------------------------------------------------

const containerStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  height: "100%",
  minHeight: 0,
  background: "#252526",
  color: "#cccccc",
  borderLeft: "1px solid #1e1e1e",
  fontFamily: "system-ui, -apple-system, sans-serif",
  fontSize: 13,
  overflow: "hidden",
};

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "8px 12px",
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "#bbbbbb",
  background: "#252526",
  borderBottom: "1px solid #1e1e1e",
};

const graphMetaStyle: CSSProperties = {
  textTransform: "none",
  letterSpacing: 0,
  fontWeight: 400,
  fontSize: 10,
  color: "#858585",
};

const adapterStripStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  flexWrap: "wrap",
  gap: 8,
  padding: "8px 12px",
  background: "#1f1f1f",
  borderBottom: "1px solid #2a2a2a",
};

const adapterNameStyle: CSSProperties = {
  fontSize: 12,
  color: "#d4d4d4",
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
};

const fixturePillStyle: CSSProperties = {
  fontSize: 10,
  padding: "2px 6px",
  borderRadius: 3,
  fontWeight: 600,
  color: "#e8c47c",
  background: "#3a2a0e",
  border: "1px solid #8f5f1e",
};

const livePillStyle: CSSProperties = {
  ...fixturePillStyle,
  color: "#7cc4e8",
  background: "#0e2a3a",
  border: "1px solid #1e5f8f",
};

const errorStyle: CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: 8,
  padding: "8px 12px",
  background: "#3a1d1d",
  borderTop: "1px solid #be1100",
  borderBottom: "1px solid #be1100",
  color: "#f48771",
  fontSize: 12,
  lineHeight: 1.45,
};

const dismissButtonStyle: CSSProperties = {
  padding: "2px 8px",
  fontSize: 11,
  background: "transparent",
  border: "1px solid #be1100",
  borderRadius: 3,
  color: "#f48771",
  cursor: "pointer",
  flexShrink: 0,
};

const phaseBannerStyle: CSSProperties = {
  padding: "8px 12px",
  fontSize: 12,
  lineHeight: 1.5,
  color: "#e8c47c",
  background: "#3a2a0e",
  borderBottom: "1px solid #8f5f1e",
};

const auditHeadingStyle: CSSProperties = {
  padding: "8px 12px 6px 12px",
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "#858585",
  borderBottom: "1px solid #1e1e1e",
  background: "#252526",
};

const historyScrollStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  overflow: "auto",
  padding: "10px 12px",
  display: "flex",
  flexDirection: "column",
  gap: 10,
};

const emptyTextStyle: CSSProperties = {
  margin: 0,
  color: "#6e6e6e",
  fontSize: 12,
  fontStyle: "italic",
};

const turnWrapStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const userBubbleStyle: CSSProperties = {
  padding: "6px 10px",
  borderRadius: 4,
  fontSize: 12,
  lineHeight: 1.4,
  color: "#e0f0ff",
  background: "#0e3a5c",
  borderLeft: "3px solid #007acc",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const systemBubbleStyle: CSSProperties = {
  padding: "6px 10px",
  borderRadius: 4,
  fontSize: 11,
  lineHeight: 1.5,
  color: "#cccccc",
  background: "#1f1f1f",
  borderLeft: "3px solid #4d4d4d",
};

const systemLabelStyle: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  color: "#858585",
  marginBottom: 4,
};

const mutedTextStyle: CSSProperties = {
  color: "#6e6e6e",
  fontStyle: "italic",
};

const changeListStyle: CSSProperties = {
  margin: 0,
  padding: 0,
  listStyle: "none",
  display: "flex",
  flexDirection: "column",
  gap: 2,
};

const changeItemStyle: CSSProperties = { lineHeight: 1.4 };

const changeLabelStyle: CSSProperties = { color: "#858585" };

const changeValuesStyle: CSSProperties = {
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
  color: "#d4d4d4",
};

const suggestionsStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 6,
  padding: "6px 12px",
  borderTop: "1px solid #1e1e1e",
  background: "#202020",
};

const chipStyle: CSSProperties = {
  padding: "3px 8px",
  fontSize: 11,
  borderRadius: 10,
  border: "1px solid #3c3c3c",
  background: "#2d2d2d",
  color: "#cccccc",
  cursor: "pointer",
};

const inputRowStyle: CSSProperties = {
  display: "flex",
  gap: 6,
  padding: "8px 12px",
  background: "#252526",
  borderTop: "1px solid #1e1e1e",
};

const inputStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  padding: "6px 8px",
  borderRadius: 3,
  border: "1px solid #3c3c3c",
  background: "#3c3c3c",
  color: "#cccccc",
  fontSize: 12,
  outline: "none",
};

const primaryButtonStyle: CSSProperties = {
  padding: "6px 12px",
  borderRadius: 3,
  border: "1px solid #0e639c",
  background: "#0e639c",
  color: "#ffffff",
  fontSize: 12,
  fontWeight: 500,
  cursor: "pointer",
  flexShrink: 0,
};

const primaryButtonDisabledStyle: CSSProperties = {
  ...primaryButtonStyle,
  background: "#2d2d2d",
  border: "1px solid #3c3c3c",
  color: "#6e6e6e",
  cursor: "not-allowed",
};

const dividerStyle: CSSProperties = {
  height: 1,
  background: "#1e1e1e",
  flexShrink: 0,
};

const approveRowStyle: CSSProperties = {
  padding: "8px 12px 12px 12px",
  background: "#252526",
};

const approveButtonStyle: CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  borderRadius: 3,
  border: "1px solid #16825d",
  background: "#16825d",
  color: "#ffffff",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
};

const approveButtonDisabledStyle: CSSProperties = {
  ...approveButtonStyle,
  background: "#2d2d2d",
  border: "1px solid #3c3c3c",
  color: "#6e6e6e",
  cursor: "not-allowed",
};