// frontend/src/types.ts
//
// Single source of truth for the frontend's view of GraphPilot backend JSON.
//
// Rules:
//   - Mirror backend Pydantic JSON projections only.
//   - No YAML parsing here or anywhere in the frontend.
//   - No duplicated validation logic.
//   - refinement_history is an AUDIT LOG, not live entities. Turn IDs are
//     historical and are never resolved against current nodes/edges/tasks.
//
// Provenance:
//   [C] confirmed by the s21/s23 master-prompt record.
//   [S] sourced from a stated contract in the record, field names pending a
//       backend excerpt. Transport is unaffected by any name mismatch; only
//       this type needs correction.
//   [O] structurally permissive so no unknown field name is invented.

export type EntityId = string; // [C] opaque; regex not re-implemented

export type SchemaVersion = "1.0" | "1.1"; // [C]

// [C] Nine literals named in the master prompt:
//   draft + lifecycle (pending, ready, running, implemented, verifying, verified)
//   + terminal (blocked, failed).
// Case-spelling is inferred; the record writes "DRAFT" in prose and
// lowercase elsewhere. Confirm against graph.py before shipping.
export type GraphStatus =
  | "draft"
  | "pending"
  | "ready"
  | "running"
  | "implemented"
  | "verifying"
  | "verified"
  | "blocked"
  | "failed";

// [C] instruction + six EntityId arrays. No timestamp, no snapshot.
export interface RefinementTurn {
  instruction: string;
  node_ids_added: EntityId[];
  node_ids_removed: EntityId[];
  edge_ids_added: EntityId[];
  edge_ids_removed: EntityId[];
  task_ids_added: EntityId[];
  task_ids_removed: EntityId[];
}

// [C-constrained] Only fields confirmed in the _compact_graph wire projection.
// The on-disk Pydantic models may carry more fields (status, evidence,
// verification command, etc.); do not extend by inference.
export interface GraphNode {
  id: EntityId;
  name: string;
  type: string;
  description: string;
}

export interface GraphEdge {
  id: EntityId;
  source: EntityId;
  target: EntityId;
  type: string;
}

export interface GraphTask {
  id: EntityId;
  title: string;
  node_id: EntityId;
  depends_on: EntityId[];
}

// [C] The browser never sees YAML; this is the JSON projection.
export interface ArchitectureGraph {
  schema_version: SchemaVersion;
  project_name: string;
  status: GraphStatus;
  nodes: GraphNode[];
  edges: GraphEdge[];
  tasks: GraphTask[];
  refinement_history: RefinementTurn[];
  approved_at: string | null; // Pydantic mode="json" ISO-8601 or null
}

// [C-constrained] is_valid confirmed ("validates but does not gate on is_valid").
// The collection field name (issues/errors/…) is not in the record; the index
// signature preserves access without inventing a name.
export type ValidationIssuePayload = unknown;

export interface ValidationReportPayload {
  is_valid: boolean;
  [key: string]: unknown;
}

// [C] Echoed by every adapter-bearing response.
export interface AdapterMetadata {
  name: string;
  is_fixture: boolean;
}

// [C]
export interface ArchitectureGenerationResponse {
  graph: ArchitectureGraph;
  validation: ValidationReportPayload;
  adapter: AdapterMetadata;
}

// [S] POST /api/architecture request body. The master prompt's
// "NL requirement -> Muse Spark adapter" implies the idea is sent to the
// backend. `requirement` is the closest match in the record; alternatives in
// the same record (`idea`, `prompt`, `text`) would need a one-line rename here
// and in client.ts. Marked [S] because api/architecture.py has not been
// excerpted. The index signature tolerates additional fields without
// pretending to know them.
export interface ArchitectureGenerateRequest {
  requirement: string;
  [key: string]: unknown;
}

// [S] Payload contents confirmed by refine_graph(current, instruction);
// JSON key names pending api/architecture.py excerpt.
export interface ArchitectureRefineRequest {
  graph: ArchitectureGraph;
  instruction: string;
}

// [S] Approve persists a graph; body may carry additional fields.
export type ArchitectureApproveRequest = ArchitectureGraph;


// [S] "graph JSON inside ArchitectureApproveResponse"; other fields open.
export interface ArchitectureApproveResponse {
  graph: ArchitectureGraph;
  validation: ValidationReportPayload;
  saved: boolean;
  saved_path: string;
}