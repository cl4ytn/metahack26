// frontend/src/components/CodeView.tsx
//
// Center-pane body for a selected node or task, VS Code "editor" styling.
//
// Rules enforced here:
//   - No fabricated code. The coding-agent adapter has no exposed endpoint
//     yet; task views state this plainly and show the task SPECIFICATION.
//   - No YAML parsing. The serialization shown is JSON.stringify of the
//     ArchitectureGraph sub-object already in memory.
//   - refinement_history is never rendered here. It belongs to CopilotPanel.
//   - `{ kind: "graph" }` is not handled here; EditorArea renders the graph.
//     A defensive fallback is shown if it is ever passed in.
//
// NOTE: imports ExplorerView / ExplorerPhase from FileExplorer for now.
// Moving them into types.ts is recommended before the App rewrite.

import { useMemo } from "react";
import type { CSSProperties } from "react";
import type { ArchitectureGraph, GraphNode, GraphTask } from "../types";
import type { ExplorerPhase, ExplorerView } from "./FileExplorer";

interface CodeViewProps {
  graph: ArchitectureGraph;
  view: ExplorerView;
  phase: ExplorerPhase;
}

// ---------------------------------------------------------------------------
// Serialization
// ---------------------------------------------------------------------------

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function CodeBlock({ source }: { source: string }) {
  // Memoised split keeps re-renders cheap when only the sidebar changes.
  const lines = useMemo(() => source.split("\n"), [source]);
  const gutterWidth = String(lines.length).length;

  return (
    <div style={codeBlockStyle} role="region" aria-label="Serialized entity">
      {lines.map((line, i) => (
        <div key={i} style={codeLineStyle}>
          <span
            style={{ ...gutterStyle, width: `${gutterWidth + 1}ch` }}
            aria-hidden="true"
          >
            {i + 1}
          </span>
          <span style={lineTextStyle}>{line.length === 0 ? " " : line}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Breadcrumb / header
// ---------------------------------------------------------------------------

function Header({
  projectName,
  trail,
  kindLabel,
}: {
  projectName: string;
  trail: string[];
  kindLabel: string;
}) {
  return (
    <div style={entityHeaderStyle}>
      <div style={breadcrumbStyle}>
        <span style={breadcrumbRootStyle}>{projectName}</span>
        {trail.map((seg, i) => (
          <span key={i} style={breadcrumbSepStyle}>
            <span style={{ opacity: 0.5 }}> › </span>
            <span>{seg}</span>
          </span>
        ))}
      </div>
      <span style={kindTagStyle}>{kindLabel}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared sub-blocks
// ---------------------------------------------------------------------------

function SectionHeading({ text }: { text: string }) {
  return <h3 style={sectionHeadingStyle}>{text}</h3>;
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div style={kvRowStyle}>
      <span style={kvLabelStyle}>{label}</span>
      <span style={kvValueStyle}>{value}</span>
    </div>
  );
}

function PhaseNote({ phase }: { phase: ExplorerPhase }) {
  const text =
    phase === "design"
      ? "Design phase — showing the task specification. Task code will be generated after approval."
      : "Implementation phase — the coding agent's output is not yet exposed by the backend. Showing the task specification.";
  return <div style={phaseNoteStyle(phase)}>{text}</div>;
}

// ---------------------------------------------------------------------------
// Node view
// ---------------------------------------------------------------------------

function NodeBody({
  node,
  tasks,
}: {
  node: GraphNode;
  tasks: GraphTask[];
}) {
  return (
    <>
      <section style={sectionStyle}>
        <SectionHeading text="Entity" />
        <KeyValue label="id" value={node.id} />
        <KeyValue label="name" value={node.name} />
        <KeyValue label="type" value={node.type} />
      </section>

      <section style={sectionStyle}>
        <SectionHeading text="Description" />
        <p style={paragraphStyle}>{node.description || "—"}</p>
      </section>

      <section style={sectionStyle}>
        <SectionHeading
          text={`Tasks attached to this node (${tasks.length})`}
        />
        {tasks.length === 0 ? (
          <p style={paragraphStyle}>No tasks reference this node.</p>
        ) : (
          <ul style={listStyle}>
            {tasks.map((t) => (
              <li key={t.id} style={listItemStyle}>
                <span style={{ fontWeight: 600 }}>{t.title}</span>
                <span style={mutedInlineStyle}> · {t.id}</span>
                {t.depends_on.length > 0 && (
                  <span style={mutedInlineStyle}>
                    {" "}· depends on {t.depends_on.join(", ")}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={sectionStyle}>
        <SectionHeading text="Serialization" />
        <CodeBlock source={prettyJson(node)} />
      </section>
    </>
  );
}

// ---------------------------------------------------------------------------
// Task view
// ---------------------------------------------------------------------------

function TaskBody({
  task,
  parentNode,
  phase,
}: {
  task: GraphTask;
  parentNode: GraphNode | undefined;
  phase: ExplorerPhase;
}) {
  return (
    <>
      <section style={sectionStyle}>
        <SectionHeading text="Task" />
        <KeyValue label="id" value={task.id} />
        <KeyValue label="title" value={task.title} />
        <KeyValue
          label="node"
          value={
            parentNode
              ? `${parentNode.name} (${parentNode.id})`
              : `${task.node_id} (not in graph.nodes)`
          }
        />
        <KeyValue
          label="depends_on"
          value={task.depends_on.length > 0 ? task.depends_on.join(", ") : "—"}
        />
      </section>

      <section style={sectionStyle}>
        <SectionHeading text="Implementation" />
        <PhaseNote phase={phase} />
      </section>

      <section style={sectionStyle}>
        <SectionHeading text="Serialization" />
        <CodeBlock source={prettyJson(task)} />
      </section>
    </>
  );
}

// ---------------------------------------------------------------------------
// Fallbacks
// ---------------------------------------------------------------------------

function GraphFallback() {
  return (
    <div style={fallbackWrapStyle}>
      <p style={fallbackTextStyle}>
        CodeView received a graph view. The graph is rendered by EditorArea;
        this body is for a selected node or task.
      </p>
    </div>
  );
}

function NotFound({ kind, id }: { kind: "node" | "task"; id: string }) {
  return (
    <div style={fallbackWrapStyle}>
      <p style={fallbackTextStyle}>
        {kind} <code>{id}</code> is not present in the current graph. It may
        have been removed by a refinement; refresh the explorer selection.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CodeView({ graph, view, phase }: CodeViewProps) {
  if (view.kind === "graph") {
    return (
      <div style={containerStyle}>
        <GraphFallback />
      </div>
    );
  }

  if (view.kind === "node") {
    const node = graph.nodes.find((n) => n.id === view.id);
    if (!node) {
      return (
        <div style={containerStyle}>
          <NotFound kind="node" id={view.id} />
        </div>
      );
    }
    const tasks = graph.tasks.filter((t) => t.node_id === node.id);
    return (
      <div style={containerStyle}>
        <Header
          projectName={graph.project_name}
          trail={[node.name]}
          kindLabel="NODE"
        />
        <div style={scrollBodyStyle}>
          <NodeBody node={node} tasks={tasks} />
        </div>
      </div>
    );
  }

  const task = graph.tasks.find((t) => t.id === view.id);
  if (!task) {
    return (
      <div style={containerStyle}>
        <NotFound kind="task" id={view.id} />
      </div>
    );
  }
  const parentNode = graph.nodes.find((n) => n.id === task.node_id);
  return (
    <div style={containerStyle}>
      <Header
        projectName={graph.project_name}
        trail={[parentNode ? parentNode.name : task.node_id, task.title]}
        kindLabel="TASK"
      />
      <div style={scrollBodyStyle}>
        <TaskBody task={task} parentNode={parentNode} phase={phase} />
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
  background: "#1e1e1e",
  color: "#d4d4d4",
  fontFamily: "system-ui, -apple-system, sans-serif",
  fontSize: 13,
  overflow: "hidden",
};

const entityHeaderStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  padding: "8px 16px",
  background: "#1e1e1e",
  borderBottom: "1px solid #2a2a2a",
  flexWrap: "wrap",
};

const breadcrumbStyle: CSSProperties = {
  fontSize: 12,
  color: "#cccccc",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};

const breadcrumbRootStyle: CSSProperties = { color: "#9cdcfe" };

const breadcrumbSepStyle: CSSProperties = { color: "#cccccc" };

const kindTagStyle: CSSProperties = {
  fontSize: 10,
  padding: "2px 6px",
  borderRadius: 3,
  letterSpacing: "0.06em",
  fontWeight: 600,
  color: "#9cdcfe",
  background: "#0e2a3a",
  border: "1px solid #1e5f8f",
};

const scrollBodyStyle: CSSProperties = {
  flex: 1,
  overflow: "auto",
  padding: "12px 16px 24px 16px",
  minHeight: 0,
};

const sectionStyle: CSSProperties = { marginBottom: 18 };

const sectionHeadingStyle: CSSProperties = {
  margin: "0 0 6px 0",
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "#858585",
};

const kvRowStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "120px 1fr",
  gap: 8,
  padding: "2px 0",
  fontSize: 13,
};

const kvLabelStyle: CSSProperties = { color: "#858585" };
const kvValueStyle: CSSProperties = {
  color: "#d4d4d4",
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
  wordBreak: "break-word",
};

const paragraphStyle: CSSProperties = {
  margin: 0,
  color: "#cccccc",
  lineHeight: 1.5,
  whiteSpace: "pre-wrap",
};

const listStyle: CSSProperties = {
  margin: 0,
  padding: "0 0 0 18px",
  color: "#cccccc",
  lineHeight: 1.6,
};

const listItemStyle: CSSProperties = { marginBottom: 2 };

const mutedInlineStyle: CSSProperties = { color: "#858585" };

const phaseNoteStyle = (phase: ExplorerPhase): CSSProperties => ({
  padding: "8px 12px",
  borderRadius: 4,
  fontSize: 12,
  lineHeight: 1.5,
  color: phase === "design" ? "#7cc4e8" : "#e8c47c",
  background: phase === "design" ? "#0e2a3a" : "#3a2a0e",
  border: `1px solid ${phase === "design" ? "#1e5f8f" : "#8f5f1e"}`,
});

const codeBlockStyle: CSSProperties = {
  background: "#181818",
  border: "1px solid #2a2a2a",
  borderRadius: 4,
  padding: "8px 0",
  overflow: "auto",
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
  fontSize: 12,
  lineHeight: 1.55,
};

const codeLineStyle: CSSProperties = {
  display: "flex",
  whiteSpace: "pre",
};

const gutterStyle: CSSProperties = {
  flexShrink: 0,
  textAlign: "right",
  padding: "0 12px 0 10px",
  color: "#5a5a5a",
  userSelect: "none",
};

const lineTextStyle: CSSProperties = {
  color: "#d4d4d4",
  paddingRight: 16,
};

const fallbackWrapStyle: CSSProperties = {
  padding: "24px 16px",
};

const fallbackTextStyle: CSSProperties = {
  margin: 0,
  color: "#858585",
  lineHeight: 1.5,
  fontSize: 13,
};