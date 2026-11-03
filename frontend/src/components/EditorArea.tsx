// frontend/src/components/EditorArea.tsx
//
// VS Code-style center pane. Owns the tab bar (Graph tab is pinned), routes
// the active view to <GraphVisualization/> or <CodeView/>, and keeps a small
// local history of opened entity tabs.
//
// Rules enforced here:
//   - No YAML parsing, no validation logic, no reinterpretation of
//     refinement_history. Those live in their own components.
//   - Tabs are a UI convenience; the single source of truth for the current
//     view is the `view` prop, owned by App.tsx. Closing a tab updates the
//     parent via `onSelect`.
//   - Entity tabs are removable; the Graph tab is not. Closing the active
//     tab falls back to the Graph view.
//   - If a refine removes an entity that still has an open tab, clicking the
//     tab shows the NotFound state from CodeView. The tab is not auto-closed;
//     the user sees a stale tab, which is honest about the entity's removal.

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import type { ArchitectureGraph } from "../types";
import { GraphVisualization } from "./GraphVisualization";
import { CodeView } from "./CodeView";
import type { ExplorerPhase, ExplorerView } from "./FileExplorer";

interface EditorAreaProps {
  graph: ArchitectureGraph | null;
  view: ExplorerView;
  phase: ExplorerPhase;
  isFixture: boolean;
  onSelect: (view: ExplorerView) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tabKey(view: ExplorerView): string {
  return view.kind === "graph" ? "graph" : `${view.kind}:${view.id}`;
}

function tabLabel(view: ExplorerView, graph: ArchitectureGraph | null): string {
  if (view.kind === "graph") return "Graph";
  if (!graph) return view.id;
  if (view.kind === "node") {
    return graph.nodes.find((n) => n.id === view.id)?.name ?? view.id;
  }
  return graph.tasks.find((t) => t.id === view.id)?.title ?? view.id;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EditorArea({
  graph,
  view,
  phase,
  isFixture,
  onSelect,
}: EditorAreaProps) {
  // openEntities is only entity tabs; the Graph tab is implicit and pinned.
  // Ordering reflects open order; the user can navigate with the explorer or
  // by clicking a tab.
  const [openEntities, setOpenEntities] = useState<ExplorerView[]>([]);

  useEffect(() => {
    if (!graph) return;
    if (view.kind === "graph") return;
    setOpenEntities((prev) => {
      const key = tabKey(view);
      if (prev.some((v) => tabKey(v) === key)) return prev;
      return [...prev, view];
    });
  }, [view, graph]);

  const closeTab = (target: ExplorerView) => {
    const targetKey = tabKey(target);
    setOpenEntities((prev) => prev.filter((v) => tabKey(v) !== targetKey));
    if (tabKey(view) === targetKey) {
      onSelect({ kind: "graph" });
    }
  };

  if (!graph) {
    return (
      <div style={containerStyle}>
        <div style={emptyWrapStyle}>
          <p style={emptyTextStyle}>
            Generate an architecture to open the editor.
          </p>
        </div>
      </div>
    );
  }

  const tabs: ExplorerView[] = [{ kind: "graph" }, ...openEntities];

  return (
    <div style={containerStyle}>
      <style>{tabCss}</style>

      <div style={tabBarStyle} role="tablist">
        {tabs.map((t) => {
          const key = tabKey(t);
          const active = key === tabKey(view);
          const closable = t.kind !== "graph";
          return (
            <div
              key={key}
              role="tab"
              aria-selected={active}
              className={"gp-tab" + (active ? " active" : "")}
              onClick={() => onSelect(t)}
              title={tabLabel(t, graph)}
            >
              <span className="label">{tabLabel(t, graph)}</span>
              {closable && (
                <span
                  className="close"
                  role="button"
                  aria-label="Close tab"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(t);
                  }}
                >
                  ×
                </span>
              )}
            </div>
          );
        })}
      </div>

      <div style={bodyStyle}>
        {view.kind === "graph" ? (
          <GraphVisualization graph={graph} isFixture={isFixture} />
        ) : (
          <CodeView graph={graph} view={view} phase={phase} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles (VS Code dark)
// ---------------------------------------------------------------------------

const tabCss = `
.gp-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 8px 0 12px;
  height: 35px;
  font-size: 13px;
  color: #9d9d9d;
  background: #2d2d2d;
  border-right: 1px solid #1e1e1e;
  border-top: 1px solid transparent;
  cursor: pointer;
  user-select: none;
  max-width: 220px;
  flex-shrink: 0;
}
.gp-tab.active {
  color: #ffffff;
  background: #1e1e1e;
  border-top: 1px solid #007acc;
}
.gp-tab:hover:not(.active) { background: #2a2d2e; }
.gp-tab .label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gp-tab .close {
  font-size: 15px;
  line-height: 1;
  opacity: 0.55;
  padding: 0 4px;
  border-radius: 3px;
}
.gp-tab .close:hover { opacity: 1; background: #4d4d4d; }
`;

const containerStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  height: "100%",
  minHeight: 0,
  background: "#1e1e1e",
  overflow: "hidden",
};

const tabBarStyle: CSSProperties = {
  display: "flex",
  alignItems: "stretch",
  background: "#252526",
  borderBottom: "1px solid #1e1e1e",
  overflowX: "auto",
  overflowY: "hidden",
  flexShrink: 0,
};

const bodyStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
};

const emptyWrapStyle: CSSProperties = {
  flex: 1,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 24,
};

const emptyTextStyle: CSSProperties = {
  margin: 0,
  color: "#858585",
  fontSize: 13,
};