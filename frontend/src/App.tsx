// frontend/src/App.tsx
//
// GraphPilot VS Code-style IDE shell.
//
// Layout: 3 columns (explorer | editor | muse) over a top toolbar and a
// bottom status strip. Every panel owns its own visuals; App owns the state
// that ties them together:
//
//   response / adapter   — last generate or refine result
//   approveResponse      — set once approve succeeds; drives phase
//   view                 — which entity/root is shown in EditorArea
//   busy / error         — request lifecycle + human-readable message
//   sessionKey           — re-mounts EditorArea + MusePanel on generate/reset
//                          so their local tab list / input reset cleanly
//                          without affecting refine (which keeps sessionKey)
//
// MusePanel contract: onRefine / onApprove MUST reject on failure. Both
// handlers below re-throw after setting error. The panel keeps the input on
// reject so the user can retry. onGenerate has no such contract.
//
// [Deferred] ExplorerPhase / ExplorerView / BusyKind live in FileExplorer and
// App locally (not types.ts). Promoting to types.ts is a six-file refactor,
// not done here for scope discipline.

import { useCallback, useState } from "react";
import type { CSSProperties } from "react";
import { FileExplorer } from "./components/FileExplorer";
import type {
  ExplorerPhase,
  ExplorerView,
} from "./components/FileExplorer";
import { EditorArea } from "./components/EditorArea";
import { MusePanel } from "./components/MusePanel";
import { StatusBar } from "./components/StatusBar";
import {
  ApiError,
  approveArchitecture,
  generateArchitecture,
  refineArchitecture,
} from "./api/client";
import type {
  AdapterMetadata,
  ArchitectureApproveResponse,
  ArchitectureGenerationResponse,
} from "./types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Mirrors client.ts's resolution so the StatusBar strip cannot lie about the
// URL the client is calling. If these ever diverge, export a resolveBackendUrl()
// from client.ts and consume it here — flagged, not done to avoid touching
// client.ts this turn.
const BACKEND_URL = (() => {
  const raw = (import.meta as any)?.env?.VITE_API_BASE_URL as
    | string
    | undefined;
  return (raw ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
})();

type BusyKind = null | "generate" | "refine" | "approve";

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [response, setResponse] =
    useState<ArchitectureGenerationResponse | null>(null);
  const [approveResponse, setApproveResponse] =
    useState<ArchitectureApproveResponse | null>(null);
  const [adapter, setAdapter] = useState<AdapterMetadata | null>(null);
  const [view, setView] = useState<ExplorerView>({ kind: "graph" });
  const [busy, setBusy] = useState<BusyKind>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionKey, setSessionKey] = useState(0);

  const phase: ExplorerPhase =
    approveResponse !== null ? "implementation" : "design";
  const graph = response?.graph ?? null;

  const handleGenerate = useCallback(async (): Promise<void> => {
    setBusy("generate");
    setError(null);
    try {
      const r = await generateArchitecture();
      setResponse(r);
      setAdapter(r.adapter);
      setApproveResponse(null);
      setView({ kind: "graph" });
      setSessionKey((k) => k + 1);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(null);
    }
  }, []);

  const handleReset = useCallback((): void => {
    setResponse(null);
    setApproveResponse(null);
    setAdapter(null);
    setView({ kind: "graph" });
    setError(null);
    setBusy(null);
    setSessionKey((k) => k + 1);
  }, []);

  // MusePanel contract: reject on failure.
  const handleRefine = useCallback(
    async (instruction: string): Promise<void> => {
      if (!response) throw new Error("No graph to refine.");
      if (approveResponse !== null) {
        throw new Error("Cannot refine after approval.");
      }
      setBusy("refine");
      setError(null);
      try {
        const r = await refineArchitecture({
          graph: response.graph,
          instruction,
        });
        setResponse(r);
        setAdapter(r.adapter);
      } catch (e) {
        setError(describeError(e));
        throw e;
      } finally {
        setBusy(null);
      }
    },
    [response, approveResponse]
  );

  // MusePanel contract: reject on failure.
  const handleApprove = useCallback(async (): Promise<void> => {
    if (!response) throw new Error("No graph to approve.");
    if (approveResponse !== null) throw new Error("Already approved.");
    setBusy("approve");
    setError(null);
    try {
      const r = await approveArchitecture({ graph: response.graph });
      setApproveResponse(r);
    } catch (e) {
      setError(describeError(e));
      throw e;
    } finally {
      setBusy(null);
    }
  }, [response, approveResponse]);

  return (
    <div style={shellStyle}>
      <TopBar
        projectName={graph?.project_name ?? null}
        subtitle={
          graph ? `${graph.schema_version} · ${graph.status}` : "no graph"
        }
        phase={phase}
        busy={busy}
        hasGraph={graph !== null}
        onGenerate={handleGenerate}
        onReset={handleReset}
      />

      <div style={cellStyle(1, 2)}>
        <FileExplorer
          graph={graph}
          phase={phase}
          view={view}
          onSelect={setView}
        />
      </div>

      <div style={cellStyle(2, 2)}>
        <EditorArea
          key={sessionKey}
          graph={graph}
          view={view}
          phase={phase}
          // Safe fallback: EditorArea only reads isFixture when graph != null,
          // which implies adapter != null (they are set together).
          isFixture={adapter?.is_fixture ?? false}
          onSelect={setView}
        />
      </div>

      <div style={cellStyle(3, 2)}>
        <MusePanel
          key={sessionKey}
          graph={graph}
          adapter={adapter}
          phase={phase}
          busy={busy}
          error={error}
          onRefine={handleRefine}
          onApprove={handleApprove}
          onDismissError={() => setError(null)}
        />
      </div>

      <div style={cellStyle("1 / -1", 3)}>
        <StatusBar
          graph={graph}
          adapter={adapter}
          phase={phase}
          backendUrl={BACKEND_URL}
          isBusy={busy !== null}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TopBar
// ---------------------------------------------------------------------------

function TopBar({
  projectName,
  subtitle,
  phase,
  busy,
  hasGraph,
  onGenerate,
  onReset,
}: {
  projectName: string | null;
  subtitle: string;
  phase: ExplorerPhase;
  busy: BusyKind;
  hasGraph: boolean;
  onGenerate: () => void | Promise<void>;
  onReset: () => void;
}) {
  return (
    <div style={topBarStyle}>
      <div style={brandStyle}>
        <span style={brandNameStyle}>GraphPilot</span>
        {projectName && (
          <span style={brandProjectStyle}>{projectName}</span>
        )}
        <span style={brandSubStyle}>{subtitle}</span>
      </div>
      <div style={topActionsStyle}>
        <span style={phasePillStyle(phase)}>{phase}</span>
        {hasGraph && (
          <button
            type="button"
            onClick={onReset}
            disabled={busy !== null}
            style={
              busy !== null ? secondaryBtnDisabledStyle : secondaryBtnStyle
            }
          >
            Reset
          </button>
        )}
        <button
          type="button"
          onClick={() => void onGenerate()}
          disabled={busy !== null}
          style={busy !== null ? primaryBtnDisabledStyle : primaryBtnStyle}
        >
          {busy === "generate"
            ? "Generating…"
            : hasGraph
            ? "Regenerate"
            : "Generate"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error text
// ---------------------------------------------------------------------------

function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case "invalid":
        return `422: ${e.message} — schema 1.0 is refused on refine. Regenerate via POST /api/architecture first.`;
      case "conflict":
        return `409: ${e.message} — the graph is not in DRAFT status. Regenerate to obtain a draft graph.`;
      case "output":
        return `502: ${e.message} — adapter output error.`;
      case "unavailable":
        return `503: ${e.message} — adapter unavailable.`;
      case "internal":
        return `500: ${e.message} — internal error.`;
      case "not_found":
        return `404: ${e.message}`;
      case "network":
        return `${e.message} — is the backend running at ${BACKEND_URL}?`;
      default:
        return `${e.message}`;
    }
  }
  if (e instanceof Error) return e.message;
  return String(e);
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const shellStyle: CSSProperties = {
  height: "100vh",
  width: "100vw",
  display: "grid",
  gridTemplateColumns: "240px minmax(0, 1fr) 320px",
  gridTemplateRows: "40px minmax(0, 1fr) 22px",
  gap: 0,
  background: "#1e1e1e",
  color: "#cccccc",
  fontFamily: "system-ui, -apple-system, sans-serif",
  fontSize: 13,
  overflow: "hidden",
  boxSizing: "border-box",
};

function cellStyle(
  col: number | string,
  row: number | string
): CSSProperties {
  return {
    gridColumn: String(col),
    gridRow: String(row),
    minHeight: 0,
    minWidth: 0,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  };
}

const topBarStyle: CSSProperties = {
  gridColumn: "1 / -1",
  gridRow: "1",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  padding: "0 12px",
  background: "#323233",
  borderBottom: "1px solid #1e1e1e",
  overflow: "hidden",
};

const brandStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  minWidth: 0,
  overflow: "hidden",
};

const brandNameStyle: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: "#e2e8f0",
  letterSpacing: "0.02em",
};

const brandProjectStyle: CSSProperties = {
  fontSize: 12,
  color: "#9cdcfe",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  maxWidth: 280,
};

const brandSubStyle: CSSProperties = {
  fontSize: 11,
  color: "#858585",
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
};

const topActionsStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  flexShrink: 0,
};

const phasePillStyle = (phase: ExplorerPhase): CSSProperties => ({
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: "0.05em",
  textTransform: "uppercase",
  padding: "2px 8px",
  borderRadius: 3,
  background: phase === "design" ? "#0e2a3a" : "#3a2a0e",
  color: phase === "design" ? "#7cc4e8" : "#e8c47c",
  border: `1px solid ${phase === "design" ? "#1e5f8f" : "#8f5f1e"}`,
});

const primaryBtnStyle: CSSProperties = {
  padding: "5px 12px",
  borderRadius: 3,
  border: "1px solid #0e639c",
  background: "#0e639c",
  color: "#ffffff",
  fontSize: 12,
  fontWeight: 500,
  cursor: "pointer",
};

const primaryBtnDisabledStyle: CSSProperties = {
  ...primaryBtnStyle,
  background: "#2d2d2d",
  border: "1px solid #3c3c3c",
  color: "#6e6e6e",
  cursor: "not-allowed",
};

const secondaryBtnStyle: CSSProperties = {
  ...primaryBtnStyle,
  background: "#2d2d2d",
  border: "1px solid #3c3c3c",
  color: "#cccccc",
};

const secondaryBtnDisabledStyle: CSSProperties = {
  ...secondaryBtnStyle,
  color: "#6e6e6e",
  cursor: "not-allowed",
};