// frontend/src/api/client.ts
//
// Thin typed wrapper for GraphPilot backend endpoints.
//
// Rules:
//   - Reads VITE_API_BASE_URL. Defaults to http://127.0.0.1:8000 if unset.
//   - Preserves the s18/s21 status ladder as typed errors:
//       422 -> "invalid"     (schema 1.0 refused on refine; ValueError path)
//       409 -> "conflict"    (non-draft status on refine)
//       502 -> "output"      (MuseSparkOutputError)
//       503 -> "unavailable" (MuseSparkUnavailableError)
//       500 -> "internal"    (MuseSparkError / other)
//       404 -> "not_found"   (GET before approve, likely)
//     Other statuses and fetch throw -> "network" / "unknown".
//   - adapter.is_fixture is surfaced verbatim on every generate/refine
//     response. The client never synthesizes a fixture flag.
//   - No retry, no auto-fallback, no hidden state, no request caching.

import type {
  ArchitectureApproveRequest,
  ArchitectureApproveResponse,
  ArchitectureGenerateRequest,
  ArchitectureGenerationResponse,
  ArchitectureRefineRequest,
} from "../types";

// ---------------------------------------------------------------------------
// Error taxonomy
// ---------------------------------------------------------------------------

export type ApiErrorCode =
  | "invalid"
  | "conflict"
  | "output"
  | "unavailable"
  | "internal"
  | "not_found"
  | "network"
  | "unknown";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number | null;
  readonly detail: unknown;

  constructor(
    code: ApiErrorCode,
    status: number | null,
    message: string,
    detail: unknown
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

function statusToCode(status: number): ApiErrorCode {
  switch (status) {
    case 404: return "not_found";
    case 409: return "conflict";
    case 422: return "invalid";
    case 500: return "internal";
    case 502: return "output";
    case 503: return "unavailable";
    default:  return "unknown";
  }
}

// ---------------------------------------------------------------------------
// Base URL
// ---------------------------------------------------------------------------

function baseUrl(): string {
  const raw = (import.meta as any)?.env?.VITE_API_BASE_URL as string | undefined;
  return (raw ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

// ---------------------------------------------------------------------------
// Transport
// ---------------------------------------------------------------------------

async function request<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown
): Promise<T> {
  const url = `${baseUrl()}${path}`;
  const init: RequestInit =
    body === undefined
      ? { method, headers: {} }
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        };

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (err) {
    throw new ApiError("network", null, `Network error: ${method} ${path}`, err);
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text.length > 0) {
    try { parsed = JSON.parse(text); } catch { parsed = text; }
  }

  if (!response.ok) {
    const detailText =
      typeof parsed === "object" && parsed !== null && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : `${method} ${path} -> ${response.status}`;
    throw new ApiError(
      statusToCode(response.status),
      response.status,
      detailText,
      parsed
    );
  }

  return parsed as T;
}

// ---------------------------------------------------------------------------
// Endpoints (contract per s18/s21 record)
// ---------------------------------------------------------------------------

// POST /api/architecture — generate
// [S] The idea is sent as { requirement: string } (see types.ts). If the
// backend's Pydantic model uses a different field name (e.g. "idea" or
// "prompt"), the first call returns 422 with the required field named in
// `detail`. Correction is one line here and one line in types.ts.
// Calling with no argument sends an empty POST — kept for backward
// compatibility with any caller that predates idea-seeding.
export function generateArchitecture(
  req?: ArchitectureGenerateRequest
): Promise<ArchitectureGenerationResponse> {
  return request<ArchitectureGenerationResponse>(
    "POST",
    "/api/architecture",
    req
  );
}

// POST /api/architecture/refine — graph-level refinement
export function refineArchitecture(
  req: ArchitectureRefineRequest
): Promise<ArchitectureGenerationResponse> {
  return request<ArchitectureGenerationResponse>(
    "POST",
    "/api/architecture/refine",
    req
  );
}

// GET /api/architecture — current persisted graph (post-approve)
// [S] Response shape reuses ArchitectureApproveResponse (both are documented
// to carry graph JSON). If GET returns a bare ArchitectureGraph, callers can
// narrow with response.graph; the transport is unaffected.
export function getArchitecture(): Promise<ArchitectureApproveResponse> {
  return request<ArchitectureApproveResponse>("GET", "/api/architecture");
}

// POST /api/architecture/approve — the only persistence point
export function approveArchitecture(
  req: ArchitectureApproveRequest
): Promise<ArchitectureApproveResponse> {
  return request<ArchitectureApproveResponse>(
    "POST",
    "/api/architecture/approve",
    req
  );
}