/**
 * Typed HTTP core (M17).
 *
 * The properties here are the ones every domain module inherits, so they are tested once at the
 * core rather than re-asserted per module: auth injection, the error contract, and the two
 * non-JSON shapes.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import {
  ApiError,
  API_KEY_STORAGE_KEY,
  getApiKey,
  requestBlobUrl,
  requestForm,
  setApiKeyProvider,
} from "@/services/http";
import { getRules } from "@/services/modules/rules";

/**
 * A real Response, not a hand-rolled stub: openapi-fetch reads `.text()`/`.clone()` internally,
 * so a partial mock tests the mock rather than the client.
 */
function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Await a call expected to fail, and return its ApiError.
 *
 * Preferred over `.catch(e => e)`: that widens the type to `ApiError | <data>` and silently
 * passes if the call unexpectedly succeeds.
 */
async function captureApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error("expected the request to reject with ApiError, but it resolved");
}

beforeEach(() => {
  localStorage.clear();
  setApiKeyProvider(() => localStorage.getItem(API_KEY_STORAGE_KEY) ?? "");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("auth middleware", () => {
  it("injects X-API-Key from the key provider", async () => {
    localStorage.setItem(API_KEY_STORAGE_KEY, "secret-key");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    await getRules();

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get("X-API-Key")).toBe("secret-key");
  });

  it("omits the header entirely when no key is set", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    await getRules();

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.has("X-API-Key")).toBe(false);
  });

  it("setApiKeyProvider swaps the key source (the M18 seam)", () => {
    setApiKeyProvider(() => "from-store");
    expect(getApiKey()).toBe("from-store");
  });
});

describe("ApiError", () => {
  it("carries status and detail, which the old client discarded", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(404, { detail: "Rule not found" })),
    );

    const error = await captureApiError(getRules());

    expect(error.status).toBe(404);
    expect(error.detail).toBe("Rule not found");
  });

  it("preserves the legacy message shape so existing error.message consumers keep working", () => {
    expect(new ApiError(404, "Rule not found").message).toBe("Rule not found");
    // No detail in the body: fall back to the same string api.js produced.
    expect(new ApiError(500, undefined).message).toBe("HTTP 500");
  });
});

describe("requestForm", () => {
  it("does not set Content-Type, so the browser can add the multipart boundary", async () => {
    localStorage.setItem(API_KEY_STORAGE_KEY, "k");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const form = new FormData();
    form.append("file", new Blob(["x"]), "x.png");
    const out = await requestForm("/api/v1/persons/p1/enroll", "POST", form);

    expect(out).toEqual({ ok: true });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers).toEqual({ "X-API-Key": "k" });
    expect(init.body).toBe(form);
  });

  it("throws ApiError with the status on failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(413, { detail: "Too large" })));

    const error = await captureApiError(requestForm("/api/v1/x", "POST", new FormData()));

    expect(error.status).toBe(413);
    expect(error.message).toBe("Too large");
  });
});

describe("requestBlobUrl", () => {
  it("returns an object URL the caller owns", async () => {
    const blob = new Blob(["binary"]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        blob: async () => blob,
      } as unknown as Response),
    );
    const createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    vi.stubGlobal("URL", { ...URL, createObjectURL });

    const url = await requestBlobUrl("/api/v1/image/active");

    expect(url).toBe("blob:mock-url");
    expect(createObjectURL).toHaveBeenCalledWith(blob);
  });
});
