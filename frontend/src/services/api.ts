import type { ArchitectureGraph, SchedulePlan, ValidationReport, RevisionImpact, ExecutionResult, VerificationResult } from '../types/graph'
export const INITIAL_GRAPH: ArchitectureGraph = {
  "schema_version": "1.0",
  "project_name": "Sample bookmarks architecture",
  "requirement": "Scale Bookmarks Service with LRU cache, rate limiting on Slug Generator, and Postgres read replica...",
  "status": "draft",
  "approved_at": null,
  "nodes": [
    {
      "id": "ui-web",
      "name": "Bookmarks Web UI",
      "type": "ui",
      "description": "Next.js Edge frontend with live bookmarking interface",
      "files": [
        "frontend/src/App.tsx",
        "frontend/src/main.tsx"
      ],
      "x": 60,
      "y": 110
    },
    {
      "id": "svc-api",
      "name": "Bookmarks HTTP API",
      "type": "api",
      "description": "Envoy ingress & gRPC API router with auth & rate limiting",
      "files": [
        "backend/app/api/bookmarks.py",
        "backend/app/api/auth.py"
      ],
      "x": 340,
      "y": 100
    },
    {
      "id": "svc-links",
      "name": "Link Service",
      "type": "service",
      "description": "High-throughput Go CRUD microservice for bookmark indexing",
      "files": [
        "services/link_service/main.go",
        "services/link_service/repo.go"
      ],
      "x": 630,
      "y": 40
    },
    {
      "id": "mod-slug",
      "name": "Slug Generator",
      "type": "module",
      "description": "Rust / WASM Murmur3 deterministic hashing and collision check",
      "files": [
        "modules/slug_gen/src/lib.rs",
        "modules/slug_gen/src/murmur.rs"
      ],
      "x": 630,
      "y": 220
    },
    {
      "id": "db-main",
      "name": "Bookmarks Database",
      "type": "database",
      "description": "PostgreSQL primary cluster with Redis LRU caching layer",
      "files": [
        "migrations/001_init.sql",
        "migrations/002_add_indexes.sql"
      ],
      "x": 930,
      "y": 130
    }
  ],
  "edges": [
    {
      "id": "edge-ui-calls-api",
      "source": "ui-web",
      "target": "svc-api",
      "type": "calls",
      "description": "mTLS 1.3 // REST + WebSocket"
    },
    {
      "id": "edge-api-depends-links",
      "source": "svc-api",
      "target": "svc-links",
      "type": "depends_on",
      "description": "gRPC / Protobuf 3"
    },
    {
      "id": "edge-links-depends-slug",
      "source": "svc-links",
      "target": "mod-slug",
      "type": "depends_on",
      "description": "WASM In-process FFI"
    },
    {
      "id": "edge-links-depends-db",
      "source": "svc-links",
      "target": "db-main",
      "type": "depends_on",
      "description": "Postgres Pool (size 50)"
    }
  ],
  "tasks": [
    {
      "id": "task-db-schema",
      "node_id": "db-main",
      "title": "Create the bookmarks table, indexes and migration",
      "description": "Establish primary schema, btree indexes on user_id, and migration script",
      "depends_on": [],
      "acceptance_criteria": [
        "schema applies cleanly",
        "indexes verified on url_hash"
      ],
      "status": "pending",
      "execution_ids": [],
      "verification_ids": [],
      "assigned_agent": "db-agent"
    },
    {
      "id": "task-slug",
      "node_id": "mod-slug",
      "title": "Implement slug generation and collision fallback",
      "description": "Murmur3 32-bit hash generator with UUIDv7 collision fallback",
      "depends_on": [],
      "acceptance_criteria": [
        "0% collision on 10k items",
        "murmur3 output deterministic"
      ],
      "status": "pending",
      "execution_ids": [],
      "verification_ids": [],
      "assigned_agent": "wasm-agent"
    },
    {
      "id": "task-link-service",
      "node_id": "svc-links",
      "title": "Implement the link service CRUD and cache lookups",
      "description": "Expose internal gRPC methods for link storing and cache verification",
      "depends_on": [
        "task-db-schema",
        "task-slug"
      ],
      "acceptance_criteria": [
        "p99 read < 10ms",
        "cache invalidation on update"
      ],
      "status": "pending",
      "execution_ids": [],
      "verification_ids": [],
      "assigned_agent": "go-micro-agent"
    },
    {
      "id": "task-api",
      "node_id": "svc-api",
      "title": "Expose the bookmarks HTTP & gRPC endpoints",
      "description": "Authenticate bearer token, validate query params, rate limit burst",
      "depends_on": [
        "task-link-service"
      ],
      "acceptance_criteria": [
        "100 rps burst allowed",
        "401 on missing token"
      ],
      "status": "pending",
      "execution_ids": [],
      "verification_ids": [],
      "assigned_agent": "api-gateway-agent"
    },
    {
      "id": "task-web-ui",
      "node_id": "ui-web",
      "title": "Build the bookmarks web UI interface",
      "description": "Responsive canvas and real-time WebSocket dashboard for link stream",
      "depends_on": [
        "task-api"
      ],
      "acceptance_criteria": [
        "loads in < 500ms",
        "responsive mobile/desktop layout"
      ],
      "status": "pending",
      "execution_ids": [],
      "verification_ids": [],
      "assigned_agent": "react-agent"
    }
  ],
  "executions": [],
  "verifications": []
}
export function withLayout(graph: ArchitectureGraph): ArchitectureGraph { return {...graph, nodes: graph.nodes.map((node, i) => ({...node, x: node.x ?? 40 + (i % 3) * 280, y: node.y ?? 40 + Math.floor(i / 3) * 200}))} }
async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
 const res = await fetch('/api'+path, {method, headers: body === undefined ? undefined : {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)})
 if (!res.ok) { const detail = await res.text(); throw new Error(method+' '+path+' failed ('+res.status+')'+(detail ? ': '+detail.slice(0,400) : '')) }
 if (res.status === 204) return undefined as T
 return res.json() as Promise<T>
}
export async function fetchArchitecture() { return withLayout(await request<ArchitectureGraph>('/architecture')) }
export async function updateArchitecture(graph: ArchitectureGraph) { return withLayout(await request<ArchitectureGraph>('/architecture', 'PUT', graph)) }
export async function approveArchitecture(revision?: number) { return withLayout(await request<ArchitectureGraph>('/architecture/approve', 'POST', {revision})) }
export async function decomposeRequirement(requirement: string) { const result = await request<{graph: ArchitectureGraph; is_valid: boolean; issues: {message: string}[]}>('/requirements/decompose', 'POST', {requirement}); return {...result, graph: withLayout(result.graph)} }
export function validateGraph() { return request<ValidationReport>('/architecture/validate', 'POST') }
export function fetchRevisionImpact(targetType: 'node' | 'task', targetId: string) { return request<RevisionImpact>('/architecture/impact', 'POST', {target_type: targetType, target_id: targetId}) }
export function fetchTaskSchedule() { return request<SchedulePlan>('/tasks/schedule') }
export function verifyTask(taskId: string, options?: {command?: string[]; project_path?: string}) { return request<{execution: ExecutionResult; verification: VerificationResult; passed: boolean}>('/tasks/'+encodeURIComponent(taskId)+'/verify', 'POST', {command: options?.command, project_path: options?.project_path}) }
export function resetTask(taskId: string) { return request<unknown>('/tasks/'+encodeURIComponent(taskId)+'/reset', 'POST') }
