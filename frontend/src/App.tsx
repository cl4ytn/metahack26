// frontend/src/App.tsx
//
// GraphPilot VS Code-style IDE shell, with an idea composer shown before the
// first graph exists.
//
// Flow:
//   empty -> composer (center pane) -> Generate(requirement) -> graph view
//   graph -> Refine (MusePanel) -> Approve (MusePanel) -> implementation
//   graph -> Regenerate (TopBar, reuses lastIdea) -> new draft, phase = design
//   any   -> Reset (TopBar) -> back to composer, sessionKey bumped
//
// Idea lifecycle:
//   `idea`     — the text currently in the composer.
//   `lastIdea` — the requirement that produced the current graph. Regenerate
//                reuses it so the graph is reproducible; to change the idea,
//                Reset first.
//
// MusePanel contract: onRefine / onApprove MUST reject on failure. Both
// handlers below re-throw after setting `error`.
//
// [Deferred, unchanged from s26] ExplorerPhase / ExplorerView / BusyKind live
// in FileExplorer and App locally, not types.ts. Promotion is a multi-file
// refactor, not done here.
//
// [Deferred, unchanged] BACKEND_URL duplicates client.ts's resolution. Export
// resolveBackendUrl() from client.ts to remove the duplication — one line,
// still pending.

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

// Mirrors client.ts's resolution so the StatusBar strip and network-error
// message cannot drift from what the client actually calls.
const BACKEND_URL = (() => {
  const raw = (import.meta as any)?.env?.VITE_API_BASE_URL as
    | string
    | undefined;
  return (raw ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
})();

type BusyKind = null | "generate" | "refine" | "approve";

const IDEA_SUGGESTIONS: string[] = [
  "A bookmark manager with tagging and full-text search",
  "A REST API for a task queue with priorities and retries",
  "A file-sync service with conflict resolution",
];

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
  const [idea, setIdea] = useState("");
  const [lastIdea, setLastIdea] = useState("");

  const phase: ExplorerPhase =
    approveResponse !== null ? "implementation" : "design";
  const graph = response?.graph ?? null;

  const handleGenerate = useCallback(
    async (requirement: string): Promise<void> => {
      const trimmed = requirement.trim();
      if (!trimmed) {
        setError("Describe the system you want to build before generating.");
        return;
      }
      setBusy("generate");
      setError(null);
      try {
        const r = await generateArchitecture({ requirement: trimmed });
        setResponse(r);
        setAdapter(r.adapter);
        setApproveResponse(null);
        setView({ kind: "graph" });
        setSessionKey((k) => k + 1);
        setLastIdea(trimmed);
        setIdea("");
      } catch (e) {
        setError(describeError(e));
      } finally {
        setBusy(null);
      }
    },
    []
  );

  const handleRegenerate = useCallback((): void => {
    if (!lastIdea) {
      setError("No previous idea to regenerate. Reset to start fresh.");
      return;
    }
    void handleGenerate(lastIdea);
  }, [lastIdea, handleGenerate]);

  const handleReset = useCallback((): void => {
    setResponse(null);
    setApproveResponse(null);
    setAdapter(null);
    setView({ kind: "graph" });
    setError(null);
    setBusy(null);
    setSessionKey((k) => k + 1);
    setIdea("");
    setLastIdea("");
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
      const r = await approveArchitecture(response.graph);
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
        onRegenerate={handleRegenerate}
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
        {graph ? (
          <EditorArea
            key={sessionKey}
            graph={graph}
            view={view}
            phase={phase}
            isFixture={adapter?.is_fixture ?? false}
            onSelect={setView}
          />
        ) : (
          <Composer
            value={idea}
            onChange={setIdea}
            onSubmit={() => void handleGenerate(idea)}
            busy={busy === "generate"}
            disabled={busy !== null}
            error={error}
          />
        )}
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
// Composer
// ---------------------------------------------------------------------------

function Composer({
  value,
  onChange,
  onSubmit,
  busy,
  disabled,
  error,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
  disabled: boolean;
  error: string | null;
}) {
  const canSubmit = !disabled && !busy && value.trim().length > 0;

  return (
    <div style={composerWrapStyle}>
      <div style={composerInnerStyle}>
        <h1 style={composerTitleStyle}>Propose an idea</h1>
        <p style={composerSubStyle}>
          Describe the system you want to build. The Muse Spark adapter will
          draft an initial ArchitectureGraph for review. Nothing is persisted
          until you approve.
        </p>

        {error && (
          <div style={composerErrorStyle} role="alert">
            <div style={{ flex: 1 }}>{error}</div>
            <button
              type="button"
              onClick={() => onChange(value)}
              style={{ display: "none" }}
              aria-hidden="true"
            />
          </div>
        )}

        <label htmlFor="gp-idea-input" style={visuallyHiddenStyle}>
          Idea
        </label>
        <textarea
          id="gp-idea-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              if (canSubmit) onSubmit();
            }
          }}
          placeholder="e.g. A bookmark manager with tagging and full-text search"
          disabled={disabled}
          style={composerTextareaStyle}
          rows={5}
          spellCheck={false}
        />

        <div style={composerChipsRowStyle}>
          {IDEA_SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onChange(s)}
              disabled={disabled}
              style={composerChipStyle}
              title={`Use "${s}"`}
            >
              {s}
            </button>
          ))}
        </div>

        <div style={composerFooterStyle}>
          <span style={composerHintStyle}>
            ⌘/Ctrl + Enter to generate · nothing is written until you approve
          </span>
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit}
            style={canSubmit ? primaryBtnStyle : primaryBtnDisabledStyle}
          >
            {busy ? "Generating…" : "Generate architecture"}
          </button>
        </div>
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
  onRegenerate,
  onReset,
}: {
  projectName: string | null;
  subtitle: string;
  phase: ExplorerPhase;
  busy: BusyKind;
  hasGraph: boolean;
  onRegenerate: () => void;
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
          <>
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
            <button
              type="button"
              onClick={onRegenerate}
              disabled={busy !== null}
              style={busy !== null ? primaryBtnDisabledStyle : primaryBtnStyle}
            >
              {busy === "generate" ? "Generating…" : "Regenerate"}
            </button>
          </>
        )}
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

// --- Composer ---

const composerWrapStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  height: "100%",
  minHeight: 0,
  padding: 24,
  background: "#1e1e1e",
  overflow: "auto",
};

const composerInnerStyle: CSSProperties = {
  width: "100%",
  maxWidth: 640,
  display: "flex",
  flexDirection: "column",
  gap: 12,
};

const composerTitleStyle: CSSProperties = {
  margin: 0,
  fontSize: 20,
  fontWeight: 600,
  color: "#e2e8f0",
};

const composerSubStyle: CSSProperties = {
  margin: 0,
  fontSize: 13,
  lineHeight: 1.5,
  color: "#9d9d9d",
};

const composerErrorStyle: CSSProperties = {
  display: "flex",
  alignItems: "flex-start",
  gap: 8,
  padding: "8px 10px",
  background: "#3a1d1d",
  border: "1px solid #be1100",
  borderRadius: 4,
  color: "#f48771",
  fontSize: 12,
  lineHeight: 1.45,
};

const composerTextareaStyle: CSSProperties = {
  width: "100%",
  minHeight: 110,
  padding: "10px 12px",
  borderRadius: 4,
  border: "1px solid #3c3c3c",
  background: "#252526",
  color: "#e2e8f0",
  fontSize: 13,
  lineHeight: 1.5,
  fontFamily: "inherit",
  resize: "vertical",
  outline: "none",
  boxSizing: "border-box",
};

const composerChipsRowStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 6,
};

const composerChipStyle: CSSProperties = {
  padding: "3px 8px",
  fontSize: 11,
  borderRadius: 10,
  border: "1px solid #3c3c3c",
  background: "#2d2d2d",
  color: "#cccccc",
  cursor: "pointer",
};

const composerFooterStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  flexWrap: "wrap",
};

const composerHintStyle: CSSProperties = {
  fontSize: 11,
  color: "#6e6e6e",
};

const visuallyHiddenStyle: CSSProperties = {
  position: "absolute",
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: "hidden",
  clip: "rect(0,0,0,0)",
  whiteSpace: "nowrap",
  border: 0,
};

// --- TopBar ---

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