// frontend/src/components/StatusBar.tsx
//
// VS Code-style bottom status strip. Persistent honesty surface: it shows
// adapter name, is_fixture, schema_version, graph status, and the resolved
// backend base URL on every render, regardless of what the center tab shows.
//
// Rules enforced here:
//   - is_fixture is never derived from anywhere except the `adapter` prop.
//     The strip does not infer, default, or synthesize a fixture flag.
//   - graph.status and graph.schema_version are printed verbatim. No
//     translation table. (GraphStatus casing is [S] in types.ts; if the
//     backend uses different casing, this strip reflects it faithfully.)
//   - When there is no graph or adapter yet, placeholders are printed
//     ("no graph", "no adapter"), not fabricated values.
//   - No YAML, no validation logic, no refinement_history rendering.

import type { CSSProperties } from "react";
import type { AdapterMetadata, ArchitectureGraph } from "../types";

// Mirrors the design/implementation phase union used elsewhere in the IDE.
// Kept local to avoid an extra cross-component import.
type PanelPhase = "design" | "implementation";

interface StatusBarProps {
  graph: ArchitectureGraph | null;
  adapter: AdapterMetadata | null;
  phase: PanelPhase;
  backendUrl: string;
  isBusy: boolean;
}

export function StatusBar({
  graph,
  adapter,
  phase,
  backendUrl,
  isBusy,
}: StatusBarProps) {
  const fixture = adapter?.is_fixture ?? null;

  return (
    <div style={containerStyle} role="status" aria-live="polite">
      <div style={leftGroupStyle}>
        <Segment title="Phase">
          <span style={phasePillStyle(phase)}>{phase}</span>
        </Segment>

        <Segment title="Adapter">
          {adapter ? (
            <span style={monoStyle}>{adapter.name}</span>
          ) : (
            <span style={mutedStyle}>no adapter</span>
          )}
        </Segment>

        <Segment title="Adapter mode">
          {fixture === null ? (
            <span style={mutedStyle}>—</span>
          ) : fixture ? (
            <span style={fixturePillStyle}>FIXTURE</span>
          ) : (
            <span style={livePillStyle}>LIVE</span>
          )}
        </Segment>

        <Segment title="Schema version">
          {graph ? (
            <span style={monoStyle}>{graph.schema_version}</span>
          ) : (
            <span style={mutedStyle}>no graph</span>
          )}
        </Segment>

        <Segment title="Graph status">
          {graph ? (
            <span style={monoStyle}>{graph.status}</span>
          ) : (
            <span style={mutedStyle}>no graph</span>
          )}
        </Segment>
      </div>

      <div style={rightGroupStyle}>
        {isBusy && <span style={busyDotStyle} aria-hidden="true" />}
        <Segment title="Backend base URL">
          <span style={monoStyle}>{backendUrl}</span>
        </Segment>
      </div>
    </div>
  );
}

function Segment({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <span style={segmentStyle} title={title}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Styles (VS Code dark status bar)
// ---------------------------------------------------------------------------

const containerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  height: 22,
  padding: "0 10px",
  background: "#007acc",
  color: "#ffffff",
  fontFamily: "system-ui, -apple-system, sans-serif",
  fontSize: 11,
  lineHeight: "22px",
  overflow: "hidden",
  userSelect: "none",
};

const leftGroupStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 14,
  minWidth: 0,
  overflow: "hidden",
};

const rightGroupStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  flexShrink: 0,
};

const segmentStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
  maxWidth: 320,
};

const monoStyle: CSSProperties = {
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
  fontSize: 11,
};

const mutedStyle: CSSProperties = {
  opacity: 0.65,
  fontStyle: "italic",
};

const fixturePillStyle: CSSProperties = {
  padding: "0 5px",
  borderRadius: 2,
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: "0.04em",
  color: "#3a2a0e",
  background: "#e8c47c",
};

const livePillStyle: CSSProperties = {
  ...fixturePillStyle,
  color: "#0e2a3a",
  background: "#7cc4e8",
};

const phasePillStyle = (phase: PanelPhase): CSSProperties => ({
  padding: "0 5px",
  borderRadius: 2,
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: "0.04em",
  color: phase === "design" ? "#0e2a3a" : "#3a2a0e",
  background: phase === "design" ? "#7cc4e8" : "#e8c47c",
});

const busyDotStyle: CSSProperties = {
  width: 8,
  height: 8,
  borderRadius: 4,
  background: "#ffffff",
  opacity: 0.85,
  animation: "none",
};