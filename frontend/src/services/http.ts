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
 * `main.js` points this at the Pinia auth store at startup (M18), which is the key's owner. The
 * localStorage default remains as the pre-wire fallback, so a request issued before bootstrap
 * completes -- or from a spec that never boots the app -- still authenticates.
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
    super(messageFor(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * Render a FastAPI `detail` as a human-readable message.
 *
 * A string detail is used as-is (what `api.js` did). An *object* detail -- FastAPI's validation
 * errors and the CTS envelopes both produce these -- is unwrapped to its `message`, falling back
 * to JSON. This is the behavior `cts.js` had; `api.js` did `body.detail || \`HTTP ${status}\``,
 * which for an object detail produced the useless "[object Object]". Adopting the better of the
 * two rather than preserving the worse one.
 */
function messageFor(status: number, detail: unknown): string {
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
    try {
      return JSON.stringify(detail);
    } catch {
      /* fall through to the status line */
    }
  }
  return `HTTP ${status}`;
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

/**
 * Untyped JSON request against an absolute API path.
 *
 * The escape hatch for domain modules that are not yet keyed to the generated types -- today
 * the CTS clients (`cts.js`, `cts_identity.js`, `cts_ph.js`, `household.js`), whose ~70 methods
 * are a separate migration. It exists so those modules stop each carrying their own copy of the
 * auth/error plumbing (four copies before M17), not as a general-purpose door: everything it
 * touches is already in `openapi.json`, so prefer `client.GET(...)` and let the types check the
 * call.
 *
 * Throws `ApiError`, so callers get the same error contract as the typed client.
 */
export async function requestJson<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const key = getApiKey();
  const headers = {
    "Content-Type": "application/json",
    ...(key ? { "X-API-Key": key } : {}),
    ...options.headers,
  };

  let response: Response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (cause) {
    // A transport failure is not an HTTP status; surface it as one recognisable message rather
    // than letting a raw TypeError reach a component (behavior carried over from cts.js).
    const reason = cause instanceof Error ? cause.message : "Unable to reach server";
    throw new Error(`Network error: ${reason}`);
  }

  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
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

async function toBlobUrl(response: Response): Promise<string> {
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  return URL.createObjectURL(await response.blob());
}

/**
 * Fetch a binary resource and return a Blob object URL.
 *
 * The caller owns the URL and must `URL.revokeObjectURL` it when done (contract carried over
 * verbatim from `api.js`).
 */
export async function requestBlobUrl(path: string): Promise<string> {
  const key = getApiKey();
  return toBlobUrl(await fetch(path, { headers: key ? { "X-API-Key": key } : {} }));
}

/** POST JSON, receive binary, return an object URL. Caller revokes. */
export async function postJsonForBlobUrl(path: string, body: unknown): Promise<string> {
  const key = getApiKey();
  return toBlobUrl(
    await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(key ? { "X-API-Key": key } : {}),
      },
      body: JSON.stringify(body),
    }),
  );
}

/** POST FormData, receive binary, return an object URL. Caller revokes. */
export async function postFormForBlobUrl(path: string, formData: FormData): Promise<string> {
  const key = getApiKey();
  return toBlobUrl(
    await fetch(path, {
      method: "POST",
      headers: key ? { "X-API-Key": key } : {},
      body: formData,
    }),
  );
}
