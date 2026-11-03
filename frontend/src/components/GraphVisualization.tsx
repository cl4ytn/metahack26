// frontend/src/components/GraphVisualization.tsx
//
// Read-only 2D force-directed render of an ArchitectureGraph JSON projection,
// using react-force-graph-2d (force-graph + d3-force under the hood).
//
// Rules enforced here:
//   - No YAML parsing (the browser only ever receives graph JSON).
//   - No duplicated validation logic (validation is a backend pass).
//   - refinement_history is an AUDIT LOG of past instructions, not live entities.
//     Turn IDs are never resolved against current nodes/edges/tasks.
//   - is_fixture is surfaced prominently on every render.
//   - Only confirmed fields are read; graph.status is printed verbatim.
//
// Dependency: `npm install react-force-graph-2d` in frontend/.
// The library mutates node objects in place (x/y/vx/vy/index) and resolves
// link.source/link.target from id strings to node refs after the first tick —
// local shapes below account for both states.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { ArchitectureGraph, RefinementTurn } from "../types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface GraphVisualizationProps {
  graph: ArchitectureGraph;
  isFixture: boolean;
}

// ---------------------------------------------------------------------------
// Local shapes for the force graph
// ---------------------------------------------------------------------------

interface FGNode {
  id: string;
  name: string;
  type: string;
  description: string;
  degree: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  index?: number;
}

interface FGLink {
  id: string;
  type: string;
  source: string | FGNode;
  target: string | FGNode;
}

interface FGGraphData {
  nodes: FGNode[];
  links: FGLink[];
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

function typeColor(type: string, alpha: number): string {
  const hue = hashString(type) % 360;
  return `hsla(${hue}, 85%, 63%, ${alpha})`;
}

function buildGraphData(graph: ArchitectureGraph): FGGraphData {
  const nodes: FGNode[] = graph.nodes.map((n) => ({
    id: n.id,
    name: n.name,
    type: n.type,
    description: n.description,
    degree: 0,
  }));
  const byId = new Map<string, FGNode>(nodes.map((n) => [n.id, n]));

  const links: FGLink[] = [];
  for (const e of graph.edges) {
    const s = byId.get(e.source);
    const t = byId.get(e.target);
    // Never invent endpoints: skip malformed edges rather than guess.
    if (!s || !t) continue;
    links.push({ id: e.id, type: e.type, source: e.source, target: e.target });
    s.degree += 1;
    t.degree += 1;
  }

  return { nodes, links };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function GraphVisualization({ graph, isFixture }: GraphVisualizationProps) {
  // react-force-graph-2d exports ForceGraphMethods, but the exact name/version
  // varies; `any` on the ref avoids version-friction without hiding anything.
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const hasFittedRef = useRef(false);

  // Rebuild only when the graph identity changes. Callers should pass a stable
  // reference to avoid re-mounting the simulation on unrelated re-renders.
  const graphData = useMemo(() => buildGraphData(graph), [graph]);

  // Explicit width/height; do not rely on the library's auto-size behaviour,
  // which has changed across versions.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDimensions({
        width: Math.max(1, Math.floor(width)),
        height: Math.max(1, Math.floor(height)),
      });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // New graph identity: clear hover, allow one auto-fit.
  useEffect(() => {
    setHoveredNodeId(null);
    hasFittedRef.current = false;
  }, [graph]);

  const hoveredNode = useMemo(() => {
    if (!hoveredNodeId) return null;
    return graphData.nodes.find((n) => n.id === hoveredNodeId) ?? null;
  }, [hoveredNodeId, graphData]);

  const handleZoomToFit = useCallback(() => {
    fgRef.current?.zoomToFit(400, 40);
  }, []);

  const handleEngineStop = useCallback(() => {
    if (hasFittedRef.current) return;
    hasFittedRef.current = true;
    // Let the first frame paint, then fit the camera to the settled layout.
    window.setTimeout(() => handleZoomToFit(), 50);
  }, [handleZoomToFit]);

  const paintNode = useCallback(
    (node: FGNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isHovered = node.id === hoveredNodeId;
      const isDimmed = hoveredNodeId !== null && !isHovered;
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const baseRadius = 3 + Math.min(node.degree, 6) * 0.7;
      const radius = isHovered ? baseRadius * 1.6 : baseRadius;
      const alpha = isDimmed ? 0.35 : 1;

      // Glow
      ctx.save();
      ctx.shadowColor = typeColor(node.type, 0.9);
      ctx.shadowBlur = (isHovered ? 18 : 10) * (1 / Math.max(globalScale, 0.5));
      ctx.fillStyle = typeColor(node.type, alpha);
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      // Label (inverse-scaled so it stays readable at any zoom)
      const fontSize = (isHovered ? 13 : 11) / globalScale;
      ctx.font = `${isHovered ? "bold " : ""}${fontSize}px system-ui, sans-serif`;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillStyle = isDimmed
        ? `rgba(148, 163, 184, ${0.25 / Math.max(globalScale, 0.5)})`
        : `rgba(226, 232, 240, ${isHovered ? 1 : 0.7})`;
      ctx.fillText(node.name, x + radius + 4 / globalScale, y);
    },
    [hoveredNodeId]
  );

  const paintNodePointerArea = useCallback(
    (node: FGNode, color: string, ctx: CanvasRenderingContext2D) => {
      const radius = 8 + Math.min(node.degree, 6) * 0.7;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, Math.PI * 2);
      ctx.fill();
    },
    []
  );

  const linkColor = useCallback(
    (link: FGLink) => {
      const src = typeof link.source === "string" ? link.source : link.source.id;
      const tgt = typeof link.target === "string" ? link.target : link.target.id;
      if (hoveredNodeId) {
        const connected = src === hoveredNodeId || tgt === hoveredNodeId;
        return connected
          ? "rgba(148, 163, 184, 0.85)"
          : "rgba(148, 163, 184, 0.06)";
      }
      return "rgba(148, 163, 184, 0.22)";
    },
    [hoveredNodeId]
  );

  const handleNodeHover = useCallback((node: FGNode | null) => {
    setHoveredNodeId(node ? node.id : null);
    const el = containerRef.current;
    if (el) el.style.cursor = node ? "pointer" : "grab";
  }, []);

  const isRenderable = dimensions.width > 0 && dimensions.height > 0;

  return (
    <div style={containerStyle}>
      <header style={headerStyle}>
        <h2 style={{ margin: 0, fontSize: "18px", color: "#e2e8f0" }}>
          {graph.project_name}{" "}
          <span style={{ color: "#94a3b8", fontWeight: 400, fontSize: "14px" }}>
            ({graph.schema_version} · {graph.status})
          </span>
        </h2>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={isFixture ? fixtureBadgeStyle : liveBadgeStyle}>
            {isFixture ? "FIXTURE — replayed, no model call" : "LIVE"}
          </span>
          <button type="button" onClick={handleZoomToFit} style={buttonStyle}>
            Reset view
          </button>
        </div>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 260px",
          gap: "12px",
        }}
      >
        <div ref={containerRef} style={canvasWrapStyle}>
          {isRenderable && (
            <ForceGraph2D
              ref={fgRef}
              width={dimensions.width}
              height={dimensions.height}
              graphData={graphData as any}
              nodeId="id"
              nodeLabel="" // built-in tooltip disabled; we show info in the sidebar
              nodeCanvasObject={paintNode as any}
              nodePointerAreaPaint={paintNodePointerArea as any}
              linkColor={linkColor as any}
              linkWidth={1}
              linkDirectionalArrowLength={3}
              linkDirectionalArrowRelPos={1}
              backgroundColor="rgba(0,0,0,0)"
              onNodeHover={handleNodeHover as any}
              onEngineStop={handleEngineStop}
              d3AlphaDecay={0.025}
              d3VelocityDecay={0.32}
            />
          )}
          <div style={hintStyle}>
            drag · scroll to zoom · {graph.nodes.length} nodes ·{" "}
            {graph.edges.length} edges
          </div>
        </div>

        <aside style={sidebarStyle}>
          <h3 style={sidebarHeadingStyle}>Node</h3>
          {hoveredNode ? (
            <dl style={dlStyle}>
              <dt style={dtStyle}>Name</dt>
              <dd style={ddStyle}>{hoveredNode.name}</dd>
              <dt style={dtStyle}>ID</dt>
              <dd style={ddStyle}>{hoveredNode.id}</dd>
              <dt style={dtStyle}>Type</dt>
              <dd style={ddStyle}>{hoveredNode.type}</dd>
              <dt style={dtStyle}>Description</dt>
              <dd style={ddStyle}>{hoveredNode.description || "—"}</dd>
              <dt style={dtStyle}>Degree</dt>
              <dd style={ddStyle}>{hoveredNode.degree}</dd>
            </dl>
          ) : (
            <p style={{ margin: 0, color: "#64748b", fontSize: "12px" }}>
              Hover a node to inspect it.
            </p>
          )}
        </aside>
      </div>

      <details style={detailsStyle}>
        <summary style={summaryStyle}>
          Entities (accessible view) · Refinement history (audit log — not
          current entities)
        </summary>
        <EntityTables graph={graph} />
        <h4 style={{ margin: "16px 0 8px 0", fontSize: "14px", color: "#e2e8f0" }}>
          Refinement history (audit log — not current entities)
        </h4>
        {graph.refinement_history.length === 0 ? (
          <p style={{ margin: 0, color: "#94a3b8" }}>
            No refinement turns recorded.
          </p>
        ) : (
          <ol style={{ margin: "0 0 0 20px", padding: 0, color: "#cbd5e1" }}>
            {graph.refinement_history.map((turn, i) => (
              <TurnItem key={i} turn={turn} index={i} />
            ))}
          </ol>
        )}
      </details>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accessible sub-views
// ---------------------------------------------------------------------------

function EntityTables({ graph }: { graph: ArchitectureGraph }) {
  return (
    <>
      <h4 style={{ margin: "0 0 8px 0", fontSize: "14px", color: "#e2e8f0" }}>
        Nodes ({graph.nodes.length})
      </h4>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>ID</th>
            <th style={thStyle}>Name</th>
            <th style={thStyle}>Type</th>
            <th style={thStyle}>Description</th>
          </tr>
        </thead>
        <tbody>
          {graph.nodes.map((n) => (
            <tr key={n.id}>
              <td style={tdStyle}>{n.id}</td>
              <td style={tdStyle}>{n.name}</td>
              <td style={tdStyle}>{n.type}</td>
              <td style={tdStyle}>{n.description}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4 style={{ margin: "16px 0 8px 0", fontSize: "14px", color: "#e2e8f0" }}>
        Edges ({graph.edges.length})
      </h4>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>ID</th>
            <th style={thStyle}>Source</th>
            <th style={thStyle}>Target</th>
            <th style={thStyle}>Type</th>
          </tr>
        </thead>
        <tbody>
          {graph.edges.map((e) => (
            <tr key={e.id}>
              <td style={tdStyle}>{e.id}</td>
              <td style={tdStyle}>{e.source}</td>
              <td style={tdStyle}>{e.target}</td>
              <td style={tdStyle}>{e.type}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4 style={{ margin: "16px 0 8px 0", fontSize: "14px", color: "#e2e8f0" }}>
        Tasks ({graph.tasks.length})
      </h4>
      <table style={tableStyle}>
        <thead>
          <tr>
            <th style={thStyle}>ID</th>
            <th style={thStyle}>Title</th>
            <th style={thStyle}>Node</th>
            <th style={thStyle}>Depends on</th>
          </tr>
        </thead>
        <tbody>
          {graph.tasks.map((t) => (
            <tr key={t.id}>
              <td style={tdStyle}>{t.id}</td>
              <td style={tdStyle}>{t.title}</td>
              <td style={tdStyle}>{t.node_id}</td>
              <td style={tdStyle}>
                {t.depends_on.length === 0 ? "—" : t.depends_on.join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function TurnItem({ turn, index }: { turn: RefinementTurn; index: number }) {
  const rows: Array<{ label: string; values: string[] }> = [
    { label: "Nodes added", values: turn.node_ids_added },
    { label: "Nodes removed", values: turn.node_ids_removed },
    { label: "Edges added", values: turn.edge_ids_added },
    { label: "Edges removed", values: turn.edge_ids_removed },
    { label: "Tasks added", values: turn.task_ids_added },
    { label: "Tasks removed", values: turn.task_ids_removed },
  ].filter((r) => r.values.length > 0);

  return (
    <li style={{ marginBottom: "8px" }}>
      <div style={{ fontWeight: 600 }}>
        Turn {index + 1}: “{turn.instruction}”
      </div>
      {rows.length === 0 ? (
        <div style={{ color: "#64748b", fontSize: "12px" }}>
          (no id changes recorded)
        </div>
      ) : (
        <ul style={{ margin: "4px 0 0 20px", padding: 0, fontSize: "12px" }}>
          {rows.map((r) => (
            <li key={r.label}>
              {r.label}: {r.values.join(", ")}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const containerStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "12px",
  padding: "16px",
  fontFamily: "system-ui, sans-serif",
  color: "#e2e8f0",
  background: "#0b0f17",
  borderRadius: "8px",
};

const headerStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
};

const fixtureBadgeStyle: CSSProperties = {
  display: "inline-block",
  padding: "4px 10px",
  borderRadius: "4px",
  fontSize: "12px",
  fontWeight: 600,
  background: "#3b2a08",
  color: "#fbbf24",
  border: "1px solid #f59e0b",
};

const liveBadgeStyle: CSSProperties = {
  ...fixtureBadgeStyle,
  background: "#0c2340",
  color: "#93c5fd",
  border: "1px solid #3b82f6",
};

const buttonStyle: CSSProperties = {
  padding: "6px 12px",
  borderRadius: "4px",
  border: "1px solid #334155",
  background: "#111827",
  color: "#e2e8f0",
  fontSize: "12px",
  cursor: "pointer",
};

const canvasWrapStyle: CSSProperties = {
  position: "relative",
  height: "520px",
  borderRadius: "6px",
  overflow: "hidden",
  background:
    "radial-gradient(ellipse at center, #131a26 0%, #070a10 70%, #05070b 100%)",
  border: "1px solid #1e293b",
};

const hintStyle: CSSProperties = {
  position: "absolute",
  left: "10px",
  bottom: "8px",
  fontSize: "11px",
  color: "#64748b",
  pointerEvents: "none",
};

const sidebarStyle: CSSProperties = {
  border: "1px solid #1e293b",
  borderRadius: "6px",
  background: "#0d131d",
  padding: "10px 12px",
  height: "520px",
  overflow: "auto",
};

const sidebarHeadingStyle: CSSProperties = {
  margin: "0 0 8px 0",
  fontSize: "12px",
  color: "#94a3b8",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const dlStyle: CSSProperties = {
  margin: 0,
  display: "grid",
  gridTemplateColumns: "auto 1fr",
  gap: "4px 10px",
  fontSize: "12px",
};

const dtStyle: CSSProperties = { color: "#64748b" };

const ddStyle: CSSProperties = {
  margin: 0,
  color: "#e2e8f0",
  wordBreak: "break-word",
};

const detailsStyle: CSSProperties = {
  border: "1px solid #1e293b",
  borderRadius: "6px",
  padding: "10px 12px",
  background: "#0d131d",
};

const summaryStyle: CSSProperties = {
  cursor: "pointer",
  fontSize: "13px",
  color: "#94a3b8",
};

const tableStyle: CSSProperties = {
  borderCollapse: "collapse",
  width: "100%",
  marginTop: "4px",
};

const thStyle: CSSProperties = {
  border: "1px solid #1e293b",
  padding: "6px 8px",
  textAlign: "left",
  fontSize: "12px",
  background: "#111827",
  color: "#cbd5e1",
};

const tdStyle: CSSProperties = {
  border: "1px solid #1e293b",
  padding: "6px 8px",
  textAlign: "left",
  verticalAlign: "top",
  fontSize: "12px",
  color: "#cbd5e1",
};