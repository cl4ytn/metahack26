// frontend/src/types.ts
//
// Single source of truth for the frontend's view of GraphPilot backend JSON.
// Rules enforced by this file:
//   - Mirror confirmed Pydantic JSON projections only.
//   - No YAML parsing here or anywhere in the frontend.
//   - No duplicated validation logic.
//   - refinement_history is an AUDIT LOG of past instructions, not live entities.
//     RefinementTurn IDs are historical; do not resolve them against current nodes/edges/tasks.
//
// Provenance markers:
//   [C]  confirmed by the s21 backend record.
//   [P]  PROVISIONAL — field presence/name pending a specific backend excerpt.
//        Do not build UI against [P] members until they are confirmed.

// ---------------------------------------------------------------------------
// Identifiers and enums
// ---------------------------------------------------------------------------

// [C] Backend applies an EntityId regex; the regex itself is not reproduced here
// and must not be re-implemented in the frontend. Treat as opaque string.
export type EntityId = string;

// [C] schema_version is a 1.0 | 1.1 literal. 1.0 loads, preserves its version on
// save, and is never auto-bumped. Refine rejects 1.0 with HTTP 422.
export type SchemaVersion = "1.0" | "1.1";

// [C] Lifecycle: pending -> ready -> running -> implemented -> verifying -> verified,
// plus blocked and failed. "draft" is required because POST /api/architecture/refine
// returns 409 when status is not DRAFT and generate_graph produces a draft graph.
// [P] The exact literal spelling/set in graph.py GraphStatus is pending confirmation.
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

// ---------------------------------------------------------------------------
// Refinement audit log
// ---------------------------------------------------------------------------

// [C] RefinementTurn: instruction + six list[EntityId] fields.
// No timestamp, no snapshot. Appended last. Invisible to the validator.
export interface RefinementTurn {
  instruction: string;
  node_ids_added: EntityId[];
  node_ids_removed: EntityId[];
  edge_ids_added: EntityId[];
  edge_ids_removed: EntityId[];
  task_ids_added: EntityId[];
  task_ids_removed: EntityId[];
}

// ---------------------------------------------------------------------------
// Graph entities
// ---------------------------------------------------------------------------

// [P] Full field declarations for GraphNode / GraphEdge / GraphTask are pending a
// graph.py model excerpt. Fields listed below are only those confirmed through the
// _compact_graph wire projection (s21 record). That projection may be a strict
// SUBSET of the on-disk / API model, so these types are intentionally minimal and
// must not be extended by inference. Any field added here requires confirmation.

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

// [C] ArchitectureGraph is the canonical contract surfaced to the browser inside
// ArchitectureGenerationResponse / ArchitectureApproveResponse. It is NEVER YAML
// in the browser.
//
// Note: a legacy on-disk 1.0 file may not contain refinement_history, but Pydantic
// fills the default and model_dump(mode="json") emits it, so the JSON projection
// the frontend receives always includes it.
//
// approved_at is a datetime serialized by Pydantic mode="json"; in JSON it is an
// ISO-8601 string when present, or null.
export interface ArchitectureGraph {
  schema_version: SchemaVersion;
  project_name: string;
  status: GraphStatus;
  nodes: GraphNode[];
  edges: GraphEdge[];
  tasks: GraphTask[];
  refinement_history: RefinementTurn[];
  approved_at: string | null;
}

// ---------------------------------------------------------------------------
// Validation payloads
// ---------------------------------------------------------------------------

// [P] ValidationIssuePayload field declarations pending a validator.py excerpt.
// Deliberately opaque so no field name is invented.
export type ValidationIssuePayload = unknown;

// [C] The report exposes is_valid; refine/generation validate but do not gate on it.
// [P] The collection field name (e.g. issues vs errors) and any other members are
// pending confirmation.
export interface ValidationReportPayload {
  is_valid: boolean;
  issues: ValidationIssuePayload[];
}

// ---------------------------------------------------------------------------
// Adapter metadata
// ---------------------------------------------------------------------------

// [C] Every adapter-bearing response echoes this. is_fixture must be surfaced on
// every call — fixture path is labeled ("fixture", "replayed", "no model call").
export interface AdapterMetadata {
  name: string;
  is_fixture: boolean;
}

// ---------------------------------------------------------------------------
// API request/response shapes
// ---------------------------------------------------------------------------

// [C] POST /api/architecture/generate and POST /api/architecture/refine return this
// shape. Validates but does not gate on is_valid; does not persist.
export interface ArchitectureGenerationResponse {
  graph: ArchitectureGraph;
  validation: ValidationReportPayload;
  adapter: AdapterMetadata;
}

// [P] Request body field names for POST /api/architecture/refine are pending an
// api/architecture.py excerpt. refine_graph(current, instruction) is the adapter
// contract, so graph + instruction is the expected pairing, but names are unconfirmed.
export interface ArchitectureRefineRequest {
  graph: ArchitectureGraph;
  instruction: string;
}

// [P] ArchitectureApproveResponse shape is pending an api/architecture.py excerpt.
// Intentionally not guessed: typed as unknown so components cannot be written
// against an unconfirmed shape without a compile-time prompt to confirm.
export type ArchitectureApproveResponse = unknown;