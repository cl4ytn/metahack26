// frontend/src/components/FileExplorer.tsx
//
// VS Code-style left sidebar: virtual project tree derived from the
// ArchitectureGraph JSON projection.
//
// Rules enforced here:
//   - Virtual view only. No filesystem access from the browser. The footer
//     says so on every render.
//   - Tree derived from graph.nodes and graph.tasks. Edges are NOT separate
//     rows; each node row's badge is its task count, and each task row's
//     badge is its depends_on count.
//   - Orphaned tasks (task.node_id not in nodes) are grouped in a distinct
//     folder, not silently dropped.
//   - In implementation phase without a wired task-execution endpoint, the
//     panel states that plainly instead of fabricating per-task status.
//   - refinement_history is NOT rendered here. It belongs to CopilotPanel,
//     labelled as an audit log.
//
// The component is width-agnostic; the parent (App.tsx grid) sets the width.

import { useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { ArchitectureGraph, GraphTask } from "../types";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type ExplorerPhase = "design" | "implementation";

export type ExplorerView =
  | { kind: "graph" }
  | { kind: "node"; id: string }
  | { kind: "task"; id: string };

interface FileExplorerProps {
  graph: ArchitectureGraph | null;
  phase: ExplorerPhase;
  view: ExplorerView;
  onSelect: (view: ExplorerView) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function typeColor(type: string): string {
  const hue = hashString(type) % 360;
  return `hsl(${hue}, 85%, 63%)`;
}

function viewEquals(a: ExplorerView, b: ExplorerView): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "graph") return true;
  return (a as { id: string }).id === (b as { id: string }).id;
}

// ---------------------------------------------------------------------------
// Tree model
// ---------------------------------------------------------------------------

interface TreeRowData {
  id: string;
  label: string;
  depth: number;
  kind: "root" | "graph" | "node" | "task" | "folder";
  view?: ExplorerView;
  nodeType?: string;
  badge?: string;
  note?: string;
  children?: TreeRowData[];
}

function buildTree(graph: ArchitectureGraph): TreeRowData {
  const nodeById = new Map(graph.nodes.map((n) => [n.id, n]));
  const tasksByNode = new Map<string, GraphTask[]>();
  const orphanTasks: GraphTask[] = [];

  for (const t of graph.tasks) {
    if (nodeById.has(t.node_id)) {
      const arr = tasksByNode.get(t.node_id) ?? [];
      arr.push(t);
      tasksByNode.set(t.node_id, arr);
    } else {
      orphanTasks.push(t);
    }
  }

  const taskRow = (t: GraphTask, depth: number): TreeRowData => ({
    id: `task:${t.id}`,
    label: t.title,
    depth,
    kind: "task",
    view: { kind: "task", id: t.id },
    badge: t.depends_on.length > 0 ? `deps ${t.depends_on.length}` : undefined,
    note:
      t.depends_on.length > 0
        ? `depends on: ${t.depends_on.join(", ")}`
        : undefined,
  });

  const nodeRows: TreeRowData[] = graph.nodes.map((n) => {
    const tasks = tasksByNode.get(n.id) ?? [];
    return {
      id: `node:${n.id}`,
      label: n.name,
      depth: 1,
      kind: "node",
      view: { kind: "node", id: n.id },
      nodeType: n.type,
      badge: tasks.length > 0 ? `${tasks.length}` : undefined,
      note: `${n.type} — ${n.description}`,
      children: tasks.map((t) => taskRow(t, 2)),
    };
  });

  const children: TreeRowData[] = [
    {
      id: "view:graph",
      label: "Graph",
      depth: 1,
      kind: "graph",
      view: { kind: "graph" },
    },
    ...nodeRows,
  ];

  if (orphanTasks.length > 0) {
    children.push({
      id: "folder:orphans",
      label: `Orphaned tasks (${orphanTasks.length})`,
      depth: 1,
      kind: "folder",
      note: "Tasks whose node_id does not match any node.",
      children: orphanTasks.map((t) => taskRow(t, 2)),
    });
  }

  return {
    id: "root",
    label: graph.project_name,
    depth: 0,
    kind: "root",
    children,
  };
}

// ---------------------------------------------------------------------------
// Row rendering
// ---------------------------------------------------------------------------

function renderIcon(row: TreeRowData): ReactNode {
  if (row.kind === "node" && row.nodeType !== undefined) {
    return (
      <span
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: 4,
          background: typeColor(row.nodeType),
        }}
      />
    );
  }
  if (row.kind === "task") {
    return (
      <span
        style={{
          display: "inline-block",
          width: 8,
          height: 8,
          border: "1px solid #858585",
          borderRadius: 1,
        }}
      />
    );
  }
  if (row.kind === "graph") {
    return <span style={{ color: "#858585", fontSize: 10 }}>◈</span>;
  }
  if (row.kind === "folder" || row.kind === "root") {
    return <span style={{ color: "#858585", fontSize: 10 }}>▣</span>;
  }
  return null;
}

function Row({
  row,
  isSelected,
  isCollapsed,
  hasChildren,
  onToggle,
  onSelect,
}: {
  row: TreeRowData;
  isSelected: boolean;
  isCollapsed: boolean;
  hasChildren: boolean;
  onToggle: () => void;
  onSelect: () => void;
}) {
  const isClickable = row.view !== undefined;
  const paddingLeft = 4 + row.depth * 12;

  return (
    <div
      className={"gp-explorer-row" + (isSelected ? " selected" : "")}
      style={{ paddingLeft, cursor: isClickable ? "pointer" : "default" }}
      onClick={isClickable ? onSelect : undefined}
      title={row.note}
    >
      <span
        className="chevron"
        onClick={(e) => {
          e.stopPropagation();
          if (hasChildren) onToggle();
        }}
      >
        {hasChildren ? (isCollapsed ? "▸" : "▾") : ""}
      </span>
      <span className="icon">{renderIcon(row)}</span>
      <span className="label">{row.label}</span>
      {row.badge && <span className="badge">{row.badge}</span>}
    </div>
  );
}

function renderRows(
  row: TreeRowData,
  collapsed: Set<string>,
  view: ExplorerView,
  onSelect: (view: ExplorerView) => void,
  toggle: (id: string) => void
): ReactNode[] {
  const out: ReactNode[] = [];
  const children = row.children ?? [];
  const hasChildren = children.length > 0;
  const isCollapsed = collapsed.has(row.id);
  const isSelected = row.view !== undefined && viewEquals(row.view, view);

  out.push(
    <Row
      key={row.id}
      row={row}
      isSelected={isSelected}
      isCollapsed={isCollapsed}
      hasChildren={hasChildren}
      onToggle={() => toggle(row.id)}
      onSelect={() => {
        if (row.view) onSelect(row.view);
      }}
    />
  );

  if (hasChildren && !isCollapsed) {
    for (const child of children) {
      out.push(...renderRows(child, collapsed, view, onSelect, toggle));
    }
  }

  return out;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FileExplorer({
  graph,
  phase,
  view,
  onSelect,
}: FileExplorerProps) {
  // "collapsed" is a set of row ids. Default = empty set = everything expanded.
  // New rows introduced by a refine (new nodes/tasks) are therefore expanded
  // by default, which matches the demo flow (add auth → see it appear).
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const tree = useMemo(() => (graph ? buildTree(graph) : null), [graph]);

  const toggle = (id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div style={containerStyle}>
      <style>{rowCss}</style>

      <header style={headerStyle}>
        <span>Explorer</span>
        <span style={phasePillStyle(phase)}>{phase}</span>
      </header>

      {phase === "implementation" && (
        <div style={bannerStyle}>
          Implementation not yet wired to a task-execution endpoint. Showing
          intended structure from the architecture graph.
        </div>
      )}

      <div style={treeBodyStyle}>
        {!tree ? (
          <p style={emptyStyle}>
            Generate an architecture to see the file tree.
          </p>
        ) : (
          <div>{renderRows(tree, collapsed, view, onSelect, toggle)}</div>
        )}
      </div>

      {tree && (
        <div style={footerStyle}>
          Virtual view — derived from architecture graph. Not a filesystem.
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const rowCss = `
.gp-explorer-row {
  display: flex;
  align-items: center;
  height: 22px;
  font-size: 13px;
  color: #cccccc;
  padding-right: 8px;
  user-select: none;
}
.gp-explorer-row:hover { background: #2a2d2e; }
.gp-explorer-row.selected { background: #094771; color: #ffffff; }
.gp-explorer-row .chevron {
  width: 14px;
  text-align: center;
  font-size: 10px;
  opacity: 0.7;
  flex-shrink: 0;
}
.gp-explorer-row .icon {
  width: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.gp-explorer-row .label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-left: 4px;
}
.gp-explorer-row .badge {
  font-size: 10px;
  color: #858585;
  margin-left: 6px;
  flex-shrink: 0;
}
`;

const containerStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  height: "100%",
  minHeight: 0,
  background: "#252526",
  borderRight: "1px solid #1e1e1e",
  color: "#cccccc",
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

const phasePillStyle = (phase: ExplorerPhase): CSSProperties => ({
  fontSize: 10,
  padding: "2px 6px",
  borderRadius: 3,
  textTransform: "none",
  letterSpacing: 0,
  fontWeight: 500,
  background: phase === "design" ? "#0e3a5c" : "#3a2a0e",
  color: phase === "design" ? "#7cc4e8" : "#e8c47c",
  border: `1px solid ${phase === "design" ? "#1e5f8f" : "#8f5f1e"}`,
});

const bannerStyle: CSSProperties = {
  padding: "8px 12px",
  fontSize: 11,
  color: "#e8c47c",
  background: "#3a2a0e",
  borderTop: "1px solid #8f5f1e",
  borderBottom: "1px solid #8f5f1e",
  lineHeight: 1.4,
};

const treeBodyStyle: CSSProperties = {
  flex: 1,
  overflow: "auto",
  padding: "4px 0",
  minHeight: 0,
};

const emptyStyle: CSSProperties = {
  margin: 0,
  padding: "12px 16px",
  fontSize: 12,
  color: "#858585",
};

const footerStyle: CSSProperties = {
  padding: "6px 12px",
  fontSize: 10,
  color: "#6e6e6e",
  borderTop: "1px solid #1e1e1e",
  background: "#202020",
  lineHeight: 1.3,
};