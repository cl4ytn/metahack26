import { useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import { edgePath } from './geometry'
import type { Node, Edge, Task } from '../types/graph'

interface Props {
  nodes: Node[]
  edges: Edge[]
  tasks?: Task[]
  selectedNodeId: string | null
  impactedNodeIds: string[]
  impactDescription: string | null
  onSelectNode: (id: string) => void
  onInspectNode: (node: Node) => void
  onClearImpact: () => void
  onNodeMove: (id: string, x: number, y: number) => void
}

function getNodeTaskBadge(nodeTasks: Task[]) {
  if (nodeTasks.length === 0) return null
  const failed = nodeTasks.filter((t) => t.status === 'failed').length
  const blocked = nodeTasks.filter((t) => t.status === 'blocked').length
  const verified = nodeTasks.filter((t) => t.status === 'verified').length
  const ready = nodeTasks.filter((t) => t.status === 'ready').length
  const total = nodeTasks.length

  if (failed > 0) {
    return { text: `Failed ${failed}`, className: 'badge-failed', nodeStatusClass: 'has-failed' }
  }
  if (blocked > 0) {
    return { text: `Blocked ${blocked}`, className: 'badge-blocked', nodeStatusClass: 'has-blocked' }
  }
  if (verified === total) {
    return { text: `Verified ${verified}/${total}`, className: 'badge-verified', nodeStatusClass: 'all-verified' }
  }
  if (ready > 0) {
    return { text: `Ready ${ready}`, className: 'badge-ready', nodeStatusClass: 'has-ready' }
  }
  return { text: `Pending ${total}`, className: 'badge-pending', nodeStatusClass: '' }
}

export function ArchitectureCanvas({
  nodes,
  edges,
  tasks = [],
  selectedNodeId,
  impactedNodeIds,
  impactDescription,
  onSelectNode,
  onInspectNode,
  onClearImpact,
  onNodeMove,
}: Props) {
  const [zoom, setZoom] = useState(1)
  const [preview, setPreview] = useState<{ id: string; x: number; y: number } | null>(null)
  const drag = useRef<{
    id: string
    startX: number
    startY: number
    x: number
    y: number
    nextX: number
    nextY: number
  } | null>(null)
  const frame = useRef<number | null>(null)

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
  }, [])

  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])

  const nodeTasksMap = useMemo(() => {
    const map = new Map<string, Task[]>()
    for (const t of tasks) {
      const list = map.get(t.node_id) || []
      list.push(t)
      map.set(t.node_id, list)
    }
    return map
  }, [tasks])

  const position = (n: Node) => (preview?.id === n.id ? preview : { x: n.x ?? 40, y: n.y ?? 40 })

  const move = (e: PointerEvent) => {
    const d = drag.current
    if (!d) return
    d.nextX = Math.max(0, d.x + (e.clientX - d.startX) / zoom)
    d.nextY = Math.max(0, d.y + (e.clientY - d.startY) / zoom)
    if (frame.current === null) {
      frame.current = requestAnimationFrame(() => {
        frame.current = null
        const current = drag.current
        if (current) setPreview({ id: current.id, x: current.nextX, y: current.nextY })
      })
    }
  }

  const finish = (cancel = false) => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
    const d = drag.current
    if (d && !cancel && (d.x !== d.nextX || d.y !== d.nextY)) {
      onNodeMove(d.id, Math.round(d.nextX), Math.round(d.nextY))
    }
    drag.current = null
    setPreview(null)
  }

  const width = Math.max(900, ...nodes.map((n) => position(n).x + 270))
  const height = Math.max(430, ...nodes.map((n) => position(n).y + 180))

  return (
    <section className="canvas" aria-label="Architecture graph">
      <div className="canvas-toolbar">
        <h2>Architecture</h2>
        <span className="muted">{nodes.length} components / {edges.length} connections</span>
        <div className="actions">
          <button aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(0.4, z - 0.1))}>-</button>
          <span>{Math.round(zoom * 100)}%</span>
          <button aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(1.5, z + 0.1))}>+</button>
          <button onClick={() => setZoom(1)}>Reset view</button>
        </div>
      </div>

      {impactDescription && (
        <div className="message">
          {impactDescription} <button onClick={onClearImpact}>Clear impact</button>
        </div>
      )}

      <p className="canvas-help">
        Select a component for details. Drag to arrange; use arrow keys to move a focused component.
      </p>

      <div className="canvas-scroll">
        <div style={{ width: width * zoom, height: height * zoom }}>
          <div className="graph-plane" style={{ width, height, transform: `scale(${zoom})` }}>
            <svg width={width} height={height} aria-hidden="true">
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
                  <path d="M0,0 L8,4 L0,8" fill="#729ca9" />
                </marker>
              </defs>
              {edges.map((e) => {
                const a = nodeMap.get(e.source)
                const b = nodeMap.get(e.target)
                if (!a || !b) return null
                const s = position(a)
                const t = position(b)
                return (
                  <path
                    key={e.id}
                    d={edgePath(s, t)}
                    fill="none"
                    stroke="#729ca9"
                    strokeWidth="1.5"
                    markerEnd="url(#arrow)"
                  />
                )
              })}
            </svg>

            {nodes.map((n) => {
              const p = position(n)
              const nodeTasks = nodeTasksMap.get(n.id) || []
              const badge = getNodeTaskBadge(nodeTasks)
              const statusClass = badge ? badge.nodeStatusClass : ''

              return (
                <div
                  key={n.id}
                  className={`graph-node ${selectedNodeId === n.id ? 'selected' : ''} ${
                    impactedNodeIds.includes(n.id) ? 'impacted' : ''
                  } ${statusClass}`}
                  style={{ left: p.x, top: p.y }}
                >
                  <button
                    className="node-select"
                    aria-pressed={selectedNodeId === n.id}
                    aria-label={`${n.name}, ${n.type}${badge ? `, ${badge.text}` : ''}. Arrow keys move; Enter selects.`}
                    onClick={() => onSelectNode(n.id)}
                    onDoubleClick={() => onInspectNode(n)}
                    onKeyDown={(e) => {
                      const directions: Record<string, [number, number]> = {
                        ArrowLeft: [-10, 0],
                        ArrowRight: [10, 0],
                        ArrowUp: [0, -10],
                        ArrowDown: [0, 10],
                      }
                      const delta = directions[e.key]
                      if (delta) {
                        e.preventDefault()
                        onNodeMove(n.id, Math.max(0, p.x + delta[0]), Math.max(0, p.y + delta[1]))
                      }
                    }}
                    onPointerDown={(e) => {
                      if (e.button !== 0) return
                      e.currentTarget.setPointerCapture(e.pointerId)
                      drag.current = {
                        id: n.id,
                        startX: e.clientX,
                        startY: e.clientY,
                        x: p.x,
                        y: p.y,
                        nextX: p.x,
                        nextY: p.y,
                      }
                    }}
                    onPointerMove={move}
                    onPointerUp={() => finish()}
                    onPointerCancel={() => finish(true)}
                  >
                    <div className="node-meta-row">
                      <small>{n.type}</small>
                      {badge && <span className={`task-badge ${badge.className}`}>{badge.text}</span>}
                    </div>
                    <strong>{n.name}</strong>
                    <span>{n.description}</span>
                  </button>
                  <button
                    className="node-inspect"
                    onClick={() => {
                      onSelectNode(n.id)
                      onInspectNode(n)
                    }}
                  >
                    Edit / {n.files.length} files
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <details className="connections">
        <summary>Connections ({edges.length})</summary>
        <ul>
          {edges.map((e) => (
            <li key={e.id}>
              {nodeMap.get(e.source)?.name ?? e.source} to {nodeMap.get(e.target)?.name ?? e.target} / {e.type}:{' '}
              {e.description}
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
