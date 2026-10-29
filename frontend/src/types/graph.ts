/**
 * Domain Models & Type Definitions for GraphPilot.
 *
 * Defines the canonical schema for:
 *  - Architecture Nodes (microservices, databases, APIs, UIs)
 *  - Directed Edges (calls, depends_on)
 *  - Deterministic Task Pipeline & Lifecycle
 *  - Subprocess Execution & Test Verification Evidence
 *  - Transitive Revision Blast Radius
 */

export type NodeType = 'service' | 'module' | 'api' | 'database' | 'ui' | 'external'

export type EdgeType = 'depends_on' | 'calls' | 'reads_from' | 'writes_to'

export type TaskStatus =
  | 'pending'      // Waiting for prerequisites or approval
  | 'ready'        // Prerequisites satisfied, ready to execute
  | 'running'      // Actively being implemented by an agent
  | 'implemented'  // Implementation finished, awaiting verification
  | 'verifying'    // Running independent subprocess verification tests
  | 'verified'     // Test suite exited 0 with ground-truth proof
  | 'blocked'      // An upstream prerequisite task failed or is blocked
  | 'failed'       // Test suite exited nonzero or timed out

export type GraphStatus = 'draft' | 'approved'

export type VerificationOutcome =
  | 'passed'
  | 'failed'
  | 'timed_out'
  | 'infrastructure_error'

/**
 * Architectural Component Node representing a deployable unit or data store.
 */
export interface Node {
  id: string
  name: string
  type: NodeType
  description: string
  files: string[]
  x?: number
  y?: number
  port?: string
  metrics?: {
    latency?: string
    uptime?: string
    throughput?: string
  }
}

/**
 * Directed connection between two architectural nodes.
 *
 * Convention: `source` depends on or calls `target`.
 */
export interface Edge {
  id: string
  source: string
  target: string
  type: EdgeType
  description: string
}

/**
 * Result claimed by a coding agent upon completing code edits.
 */
export interface ExecutionResult {
  id: string
  task_id: string
  agent_name: string
  external_run_id?: string | null
  started_at: string
  finished_at?: string | null
  changed_files: string[]
  diff: string
  agent_reported_success?: boolean | null
  timed_out: boolean
  error?: string | null
}

/**
 * Empirical test verification produced strictly by an independent subprocess.
 *
 * Ground-truth rule: Only exit_code === 0 constitutes a valid pass.
 */
export interface VerificationResult {
  graph_revision?: number
  is_simulation?: boolean
  project_path?: string
  id: string
  task_id: string
  execution_id: string
  command: string
  outcome: VerificationOutcome
  exit_code?: number | null
  stdout: string
  stderr: string
  started_at: string
  finished_at?: string | null
  passed: boolean
}

/**
 * Deterministic unit of work assigned to an architectural node.
 */
export interface Task {
  id: string
  title: string
  description: string
  node_id: string
  depends_on: string[]
  acceptance_criteria: string[]
  status: TaskStatus
  execution_ids: string[]
  verification_ids: string[]
  assigned_agent?: string
  duration?: string
}

/**
 * Complete Project Architecture specification containing nodes, edges,
 * task schedules, and tamper-proof verification history.
 */
export interface ArchitectureGraph {
  revision?: number
  approved_revision?: number | null
  is_fixture?: boolean
  schema_version: '1.0'
  project_name: string
  requirement: string
  status: GraphStatus
  approved_at?: string | null
  nodes: Node[]
  edges: Edge[]
  tasks: Task[]
  executions: ExecutionResult[]
  verifications: VerificationResult[]
}

/**
 * Topological scheduling plan calculated from the DAG.
 */
export interface SchedulePlan {
  ready: string[]
  blocked: string[]
  waiting: string[]
  is_approved: boolean
}

/**
 * Individual DAG validation issue (e.g. cycle, missing file, dangling reference).
 */
export interface ValidationIssue {
  severity: 'error' | 'warning'
  entity_id: string
  message: string
}

export interface ValidationReport {
  is_valid: boolean
  issues: ValidationIssue[]
}

/**
 * Calculated blast radius when revising a node or task.
 */
export interface RevisionImpact {
  target_id: string
  target_type: 'node' | 'task'
  impacted_node_ids: string[]
  impacted_task_ids: string[]
  blast_radius_percentage: number
  description: string
}
