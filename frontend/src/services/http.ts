/**
 * The one HTTP core (M17).
 *
 * A single typed `openapi-fetch` client keyed on the generated `paths` type, replacing the six
 * copies of fetch/error boilerplate in `api.js`. Request paths, params, bodies and responses are
 * checked at compile time against `openapi.json`; the client owns query/path serialization, so
 * the raw-interpolation encoding bugs are gone by construction.
 *
 * Domain modules under `src/services/modules/` are the only intended callers. Components never
 * call `fetch` directly.
 *
 * Regenerate types with `npm run generate:api` after any backend contract change; CI diff-gates
 * both `openapi.json` and the generated types.
 */

import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/generated/api-types";

/**
 * Note the empty baseUrl: the OpenAPI path keys already carry the `/api/v1` prefix (the routers
 * are mounted under it), so the paths are absolute already. Setting `baseUrl: "/api/v1"` would
 * request `/api/v1/api/v1/...`. `/metrics` is the one non-prefixed path.
 */
export const client = createClient<paths>({
  baseUrl: "",
  // openapi-fetch captures globalThis.fetch when the client is constructed, at module load.
  // Resolving it per call instead keeps `vi.stubGlobal("fetch", ...)` working in specs, and
  // costs one property lookup per request.
  fetch: (request) => globalThis.fetch(request),
});

// ─── Auth ──────────────────────────────────────────────────────────────────

export const API_KEY_STORAGE_KEY = "cc_api_key";

type ApiKeyProvider = () => string;

let apiKeyProvider: ApiKeyProvider = () => localStorage.getItem(API_KEY_STORAGE_KEY) ?? "";

/**
 * Swap the source of the API key.
 *
 * The default reads localStorage directly, matching `api.js`'s historical behavior. M18 points
 * this at the Pinia auth store; this seam exists so that is a one-line change rather than a
 * rewrite of the middleware.
 */
export function setApiKeyProvider(provider: ApiKeyProvider): void {
  apiKeyProvider = provider;
}

export function getApiKey(): string {
  return apiKeyProvider();
}

const authMiddleware: Middleware = {
  onRequest({ request }) {
    const key = apiKeyProvider();
    if (key) request.headers.set("X-API-Key", key);
    return request;
  },
};

client.use(authMiddleware);

// ─── Errors ────────────────────────────────────────────────────────────────

/**
 * A failed HTTP response.
 *
 * `message` deliberately preserves the shape `api.js` threw (`body.detail` or `HTTP <status>`),
 * because views and composables display `error.message` directly. `status` and `detail` are the
 * new information: the old client discarded both, so callers could not distinguish a 404 from a
 * 500 without parsing the string.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" && detail ? detail : `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Extract FastAPI's `{detail: ...}` without assuming the error body is JSON at all. */
async function errorDetail(response: Response): Promise<unknown> {
  try {
    const body = await response.json();
    return (body as { detail?: unknown })?.detail ?? body;
  } catch {
    return undefined;
  }
}

/**
 * Await an openapi-fetch call and return `data`, or throw `ApiError`.
 *
 * openapi-fetch resolves to `{data, error, response}` rather than throwing, which is a better
 * default; every existing caller of `api.js` is written against throw-on-error, so modules
 * funnel through here to keep that contract. Takes the un-awaited call so `T` is inferred from
 * the generated response type at each call site.
 */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) {
    const detail = (error as { detail?: unknown })?.detail ?? error;
    throw new ApiError(response.status, detail);
  }
  // 204 has no body: `api.js` returned null, and callers branch on it.
  if (response.status === 204) return null as T;
  return data as T;
}

// ─── Non-JSON helpers ──────────────────────────────────────────────────────
//
// The shapes openapi-fetch does not model: multipart uploads and binary bodies. They still go
// through one implementation each rather than being re-copied per call site.

/**
 * Multipart POST/PUT. Returns parsed JSON, or null on 204.
 *
 * `Content-Type` is deliberately not set: the browser must add its own multipart boundary.
 */
export async function requestForm<T = unknown>(
  path: string,
  method: "POST" | "PUT",
  formData: FormData,
): Promise<T> {
  const key = getApiKey();
  const response = await fetch(path, {
    method,
    headers: key ? { "X-API-Key": key } : {},
    body: formData,
  });
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
}

/**
 * Fetch a binary resource and return a Blob object URL.
 *
 * The caller owns the URL and must `URL.revokeObjectURL` it when done (contract carried over
 * verbatim from `api.js`).
 */
export async function requestBlobUrl(path: string): Promise<string> {
  const key = getApiKey();
  const response = await fetch(path, { headers: key ? { "X-API-Key": key } : {} });
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  return URL.createObjectURL(await response.blob());
}
