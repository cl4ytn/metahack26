import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { serializeGraph } from './services/export'
import { parseCommand } from './services/commandTokenizer'
import type { ArchitectureGraph, Node } from './types/graph'
import {
  INITIAL_GRAPH,
  fetchArchitecture,
  updateArchitecture,
  approveArchitecture,
  decomposeRequirement,
  verifyTask,
  resetTask,
  fetchRevisionImpact,
} from './services/api'
import { ArchitectureCanvas } from './components/ArchitectureCanvas'

interface TaskConfig {
  command: string
  projectPath: string
}

const DEFAULT_TASK_CONFIGS: Record<string, TaskConfig> = {
  'task-db-schema': {
    projectPath: 'sample_project',
    command: 'python -m unittest test_db_schema.py',
  },
  'task-slug': {
    projectPath: 'sample_project',
    command: 'python -m unittest test_slug.py',
  },
  'task-link-service': {
    projectPath: 'sample_project',
    command: 'python -m unittest',
  },
  'task-api': {
    projectPath: 'sample_project',
    command: 'python -m unittest',
  },
  'task-web-ui': {
    projectPath: 'sample_project',
    command: 'python -m unittest',
  },
}

function getTaskPresets(taskId: string) {
  if (taskId === 'task-db-schema') {
    return [
      { label: 'Sample unittest', cmd: 'python -m unittest test_db_schema.py', path: 'sample_project' },
      { label: 'Pytest format', cmd: 'python -m pytest test_db_schema.py -q', path: 'sample_project' },
      { label: 'JSON array', cmd: '["python", "-m", "unittest", "test_db_schema.py"]', path: 'sample_project' },
    ]
  }
  if (taskId === 'task-slug') {
    return [
      { label: 'Sample unittest', cmd: 'python -m unittest test_slug.py', path: 'sample_project' },
      { label: 'Pytest format', cmd: 'python -m pytest test_slug.py -q', path: 'sample_project' },
      { label: 'JSON array', cmd: '["python", "-m", "unittest", "test_slug.py"]', path: 'sample_project' },
    ]
  }
  return [
    { label: 'Sample unittest', cmd: 'python -m unittest', path: 'sample_project' },
    { label: 'Pytest format', cmd: 'python -m pytest -q', path: '.' },
    { label: 'JSON array', cmd: '["python", "-m", "unittest"]', path: 'sample_project' },
  ]
}

function Dialog({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current!
    const previous = document.activeElement as HTMLElement
    dialog.showModal()
    return () => {
      dialog.close()
      previous?.focus()
    }
  }, [])
  return (
    <dialog ref={ref} onCancel={onClose} aria-label={title}>
      <header>
        <h2>{title}</h2>
        <button onClick={onClose} aria-label="Close dialog">
          Close
        </button>
      </header>
      {children}
    </dialog>
  )
}

export function App() {
  const [graph, setGraph] = useState<ArchitectureGraph>(INITIAL_GRAPH)
  const [requirement, setRequirement] = useState(INITIAL_GRAPH.requirement)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [tab, setTab] = useState(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search)
      const t = params.get('tab')
      if (t && ['graph', 'tasks', 'evidence', 'yaml'].includes(t)) {
        return t
      }
    }
    return 'graph'
  })
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [selectedTask, setSelectedTask] = useState<string | null>('task-db-schema')
  const [board, setBoard] = useState(false)
  const [modal, setModal] = useState<'approve' | 'node' | null>(null)
  const [editing, setEditing] = useState<Node | null>(null)
  const [impact, setImpact] = useState<{ ids: string[]; description: string }>({
    ids: [],
    description: '',
  })
  const [notice, setNotice] = useState('')

  // Per-task configuration memory
  const [taskConfigs, setTaskConfigs] = useState<Record<string, TaskConfig>>(DEFAULT_TASK_CONFIGS)
  const [projectPath, setProjectPath] = useState('sample_project')
  const [command, setCommand] = useState('python -m unittest test_db_schema.py')

  useEffect(() => {
    let active = true
    fetchArchitecture()
      .then((g) => {
        if (active) {
          setGraph(g)
          setRequirement(g.requirement)
          setConnected(true)
          if (g.tasks.length > 0) {
            const firstTask = g.tasks[0].id
            setSelectedTask(firstTask)
            setSelectedNode(g.tasks[0].node_id)
            const cfg = DEFAULT_TASK_CONFIGS[firstTask]
            if (cfg) {
              setProjectPath(cfg.projectPath)
              setCommand(cfg.command)
            }
          }
        }
      })
      .catch((e) => {
        if (active) setError(e.message)
      })
    return () => {
      active = false
    }
  }, [])

  const run = async (work: () => Promise<void>) => {
    setBusy(true)
    setError('')
    try {
      await work()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  const load = (g: ArchitectureGraph) => {
    setGraph(g)
    setRequirement(g.requirement)
    setConnected(true)
    setDirty(false)
  }

  const task = graph.tasks.find((t) => t.id === selectedTask)
  const node = graph.nodes.find((n) => n.id === selectedNode)
  const executions = graph.executions.filter((e) => e.task_id === selectedTask)
  const verifications = graph.verifications.filter((v) => v.task_id === selectedTask)

  const save = async () => {
    const saved = await updateArchitecture({ ...graph, requirement })
    load(saved)
    return saved
  }

  const switchTask = (taskId: string | null) => {
    setSelectedTask(taskId)
    if (taskId) {
      const cfg =
        taskConfigs[taskId] ||
        DEFAULT_TASK_CONFIGS[taskId] || {
          projectPath: 'sample_project',
          command: 'python -m unittest',
        }
      setProjectPath(cfg.projectPath)
      setCommand(cfg.command)
    }
  }

  const handleProjectPathChange = (newPath: string) => {
    setProjectPath(newPath)
    if (selectedTask) {
      setTaskConfigs((prev) => ({
        ...prev,
        [selectedTask]: {
          command: prev[selectedTask]?.command || command,
          projectPath: newPath,
        },
      }))
    }
  }

  const handleCommandChange = (newCmd: string) => {
    setCommand(newCmd)
    if (selectedTask) {
      setTaskConfigs((prev) => ({
        ...prev,
        [selectedTask]: {
          projectPath: prev[selectedTask]?.projectPath || projectPath,
          command: newCmd,
        },
      }))
    }
  }

  const verify = (id: string) =>
    run(async () => {
      const argv = parseCommand(command)
      await verifyTask(id, { command: argv, project_path: projectPath })
      load(await fetchArchitecture())
    })

  const reset = (id: string) =>
    run(async () => {
      await resetTask(id)
      load(await fetchArchitecture())
    })

  const select = (id: string) => {
    setSelectedNode(id)
    const matchingTask = graph.tasks.find((t) => t.node_id === id)?.id ?? null
    switchTask(matchingTask)
  }

  const evidence = (
    <section className="evidence">
      <h2>{task?.title ?? 'Task evidence'}</h2>
      {!task ? (
        <p>Select a task to review its criteria and recorded execution history.</p>
      ) : (
        <>
          <p className="muted">
            {task.status} / {task.id}
          </p>
          <p>{task.description}</p>
          <h3>Acceptance criteria</h3>
          <ul>
            {task.acceptance_criteria.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <h3>Prerequisites</h3>
          <p>{task.depends_on.length ? task.depends_on.join(', ') : 'None'}</p>

          <label htmlFor="project-path">Server project directory (e.g. sample_project)</label>
          <input
            id="project-path"
            value={projectPath}
            onChange={(e) => handleProjectPathChange(e.target.value)}
          />

          <label htmlFor="check-command">Check command (natural syntax or JSON array)</label>
          <div className="command-chips" role="group" aria-label="Command presets">
            <span className="muted" style={{ fontSize: '11px', alignSelf: 'center' }}>
              Presets:
            </span>
            {getTaskPresets(task.id).map((chip) => (
              <button
                key={chip.label}
                type="button"
                className="chip-button"
                onClick={() => {
                  handleCommandChange(chip.cmd)
                  if (chip.path) handleProjectPathChange(chip.path)
                }}
                title={`Fill: ${chip.cmd} in ${chip.path}`}
              >
                {chip.label}
              </button>
            ))}
          </div>
          <input
            id="check-command"
            value={command}
            onChange={(e) => handleCommandChange(e.target.value)}
            style={{ width: '100%' }}
            placeholder="e.g. python -m unittest test_db_schema.py"
          />

          <p className="muted">
            Runs on the server in its configured project directory without invoking a shell. A successful command records exit code 0; review coverage against each criterion.
          </p>

          <div className="actions">
            <button
              disabled={
                !connected ||
                busy ||
                dirty ||
                graph.status !== 'approved' ||
                !['ready', 'implemented', 'failed', 'verified'].includes(task.status)
              }
              onClick={() => verify(task.id)}
            >
              Run configured checks
            </button>
            <button disabled={!connected || busy || dirty} onClick={() => reset(task.id)}>
              Reset task
            </button>
          </div>

          {dirty && <p>Save your edits before running checks.</p>}

          <h3>Verification history ({verifications.length})</h3>
          {!verifications.length && <p>No verification results recorded.</p>}
          {verifications.map((v) => (
            <article key={v.id}>
              <h4>
                {v.outcome} / exit {v.exit_code ?? 'unavailable'}
              </h4>
              <p>
                Graph revision: {v.graph_revision ?? 'not recorded'} / simulation:{' '}
                {String(v.is_simulation ?? false)} / project: {v.project_path ?? 'not recorded'}
              </p>
              <p className="muted">
                {v.started_at} to {v.finished_at ?? 'unfinished'}
              </p>
              <pre>{v.command}</pre>
              <h4>Standard output</h4>
              <pre>{v.stdout || '(empty)'}</pre>
              <h4>Standard error</h4>
              <pre>{v.stderr || '(empty)'}</pre>
            </article>
          ))}

          <h3>Execution history ({executions.length})</h3>
          {!executions.length && <p>No executions recorded.</p>}
          {executions.map((e) => (
            <article key={e.id}>
              <h4>{e.agent_name}</h4>
              <p>
                {e.started_at} to {e.finished_at ?? 'unfinished'}
              </p>
              <p>
                Agent reported success: {String(e.agent_reported_success ?? 'unknown')} / timed out:{' '}
                {String(e.timed_out)}
              </p>
              {e.error && <p>{e.error}</p>}
              <p>Changed files: {e.changed_files.join(', ') || 'None recorded'}</p>
              <pre>{e.diff || 'No diff recorded'}</pre>
            </article>
          ))}
        </>
      )}
    </section>
  )

  const tasks = (
    <div className="task-list">
      {graph.tasks.map((t) => (
        <button
          key={t.id}
          className={t.id === selectedTask ? 'selected' : ''}
          onClick={() => {
            switchTask(t.id)
            setSelectedNode(t.node_id)
          }}
        >
          <span>{t.title}</span>
          <small>{t.status}</small>
        </button>
      ))}
    </div>
  )

  return (
    <div className="app-shell">
      <header className="top">
        <div>
          <strong className="brand">GraphPilot</strong>
          <h1>{graph.project_name}</h1>
          <p className="muted">
            {connected
              ? `${graph.status}${dirty ? ' / unsaved edits' : ''}`
              : 'Sample architecture / server unavailable'}
          </p>
        </div>
        <div className="actions">
          <button disabled={busy} onClick={() => run(async () => load(await fetchArchitecture()))}>
            Reload saved graph
          </button>
          <button
            disabled={!connected || busy || !dirty}
            onClick={() =>
              run(async () => {
                await save()
                setNotice('Graph saved')
              })
            }
          >
            Save changes
          </button>
          <button
            className="primary"
            disabled={!connected || busy || graph.status === 'approved'}
            onClick={() => setModal('approve')}
          >
            Review & approve
          </button>
        </div>
      </header>

      <div className="requirement">
        <label htmlFor="requirement">Requirement</label>
        <textarea
          disabled={busy}
          id="requirement"
          value={requirement}
          onChange={(e) => {
            setRequirement(e.target.value)
            setDirty(true)
          }}
        />
        <button
          disabled={busy || !requirement.trim()}
          onClick={() =>
            run(async () => {
              const result = await decomposeRequirement(requirement)
              load(result.graph)
              if (!result.is_valid) setError(result.issues.map((i) => i.message).join('; '))
              setImpact({ ids: [], description: '' })
            })
          }
        >
          {busy ? 'Working...' : 'Create draft'}
        </button>
      </div>

      {graph.is_fixture && (
        <div className="message">
          Sample architecture - fixed example, no model call. Checks run real test commands in configured project directories.
        </div>
      )}
      {error && (
        <div className="message error" role="alert">
          {error}
        </div>
      )}
      {!connected && (
        <div className="message">
          This sample illustrates graph editing. Approval and checks require a working server.
        </div>
      )}
      {notice && (
        <div className="message" role="status">
          {notice}
        </div>
      )}

      <nav aria-label="Workspace">
        {['graph', 'tasks', 'evidence', 'export'].map((t) => (
          <button
            key={t}
            aria-current={tab === t ? 'page' : undefined}
            onClick={() => setTab(t)}
          >
            {t === 'export' ? 'YAML-compatible JSON' : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>

      <div className={`workspace ${tab === 'evidence' || tab === 'export' ? 'wide' : ''}`}>
        <main inert={busy}>
          {tab === 'graph' && (
            <>
              <ArchitectureCanvas
                nodes={graph.nodes}
                edges={graph.edges}
                tasks={graph.tasks}
                selectedNodeId={selectedNode}
                impactedNodeIds={impact.ids}
                impactDescription={impact.description}
                onSelectNode={select}
                onInspectNode={(n) => {
                  setEditing({ ...n })
                  setModal('node')
                }}
                onClearImpact={() => setImpact({ ids: [], description: '' })}
                onNodeMove={(id, x, y) => {
                  setGraph((g) => ({
                    ...g,
                    status: 'draft',
                    approved_at: null,
                    nodes: g.nodes.map((n) => (n.id === id ? { ...n, x, y } : n)),
                  }))
                  setDirty(true)
                }}
              />
              <button
                className="board-toggle"
                aria-expanded={board}
                onClick={() => setBoard(!board)}
              >
                {board ? 'Hide' : 'Show'} task board / {graph.tasks.length} tasks
              </button>
              {board && tasks}
            </>
          )}

          {tab === 'tasks' && (
            <>
              <h2>Tasks</h2>
              {tasks}
            </>
          )}

          {tab === 'evidence' && (
            <>
              <label htmlFor="task-select">Task</label>
              <select
                id="task-select"
                value={selectedTask ?? ''}
                onChange={(e) => switchTask(e.target.value || null)}
              >
                <option value="">Select task</option>
                {graph.tasks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.title}
                  </option>
                ))}
              </select>
              {evidence}
            </>
          )}

          {tab === 'export' && (
            <>
              <h2>Complete graph export</h2>
              <p>JSON syntax is valid YAML 1.2. All strings are escaped by the JSON serializer.</p>
              <p>Includes nodes, tasks, coordinates and recorded evidence. Unsaved edits are included.</p>
              <button
                onClick={() =>
                  run(async () => {
                    await navigator.clipboard.writeText(serializeGraph(graph))
                    setNotice('YAML copied')
                  })
                }
              >
                Copy export
              </button>
              <pre>{serializeGraph(graph)}</pre>
            </>
          )}
        </main>

        {tab !== 'evidence' && tab !== 'export' && (
          <aside inert={busy} aria-label="Selection details">
            {node && (
              <section>
                <h2>{node.name}</h2>
                <p>{node.description}</p>
                <p className="muted">
                  {node.type} / {node.files.length} files
                </p>
                <div className="actions">
                  <button
                    onClick={() => {
                      setEditing({ ...node })
                      setModal('node')
                    }}
                  >
                    Edit component
                  </button>
                  <button
                    disabled={!connected || busy || dirty}
                    onClick={() =>
                      run(async () => {
                        const r = await fetchRevisionImpact('node', node.id)
                        setImpact({ ids: r.impacted_node_ids, description: r.description })
                      })
                    }
                  >
                    Show change impact
                  </button>
                </div>
              </section>
            )}

            {task ? (
              <>
                <h3>Related task</h3>
                <p>{task.title}</p>
                <p className="muted">
                  {task.status} / {verifications.length} checks recorded
                </p>
                <button onClick={() => setTab('evidence')}>Open evidence</button>
              </>
            ) : (
              <p>Select a component or task to see details.</p>
            )}
          </aside>
        )}
      </div>

      {modal === 'approve' && (
        <Dialog title="Approve this architecture" onClose={() => setModal(null)}>
          <p>
            {graph.nodes.length} components / {graph.tasks.length} tasks
          </p>
          <p>
            Save current edits and validate the graph on the server before approving. Approval enables the server's dependency schedule; it does not prove implementation or acceptance criteria.
          </p>
          <button
            disabled={busy || !connected}
            onClick={() =>
              run(async () => {
                const saved = await save()
                load(await approveArchitecture(saved.revision))
                setModal(null)
              })
            }
          >
            Save and approve
          </button>
        </Dialog>
      )}

      {modal === 'node' && editing && (
        <Dialog title="Edit component" onClose={() => setModal(null)}>
          <label htmlFor="node-name">Name</label>
          <input
            id="node-name"
            value={editing.name}
            onChange={(e) => setEditing({ ...editing, name: e.target.value })}
          />
          <label htmlFor="node-description">Description</label>
          <textarea
            id="node-description"
            value={editing.description}
            onChange={(e) => setEditing({ ...editing, description: e.target.value })}
          />
          <label htmlFor="node-files">Files (one per line)</label>
          <textarea
            id="node-files"
            value={editing.files.join('\n')}
            onChange={(e) => setEditing({ ...editing, files: e.target.value.split('\n') })}
          />
          <button
            disabled={!editing.name.trim()}
            onClick={() => {
              setGraph((g) => ({
                ...g,
                status: 'draft',
                approved_at: null,
                nodes: g.nodes.map((n) =>
                  n.id === editing.id ? { ...editing, files: editing.files.filter(Boolean) } : n
                ),
              }))
              setDirty(true)
              setModal(null)
            }}
          >
            Apply edits
          </button>
        </Dialog>
      )}
    </div>
  )
}

export default App
