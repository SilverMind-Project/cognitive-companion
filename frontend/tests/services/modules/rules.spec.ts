/**
 * Pilot domain modules on the typed client.
 *
 * Beyond happy/error paths, the load-bearing assertion here is serialization: the old client
 * built URLs by interpolating values straight into template strings, so any value containing a
 * URL-significant character produced a wrong request. The typed client owns encoding, and these
 * tests pin that it actually happens.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { ApiError, API_KEY_STORAGE_KEY } from "@/services/http";
import { getSampleImage, getPipelineRuns } from "@/services/modules/pipeline";
import {
  getRule,
  getRules,
  deleteRule,
  executeRule,
  replaceRuleEdges,
} from "@/services/modules/rules";
import { getWorkflows } from "@/services/modules/workflows";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(status, body));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The URL openapi-fetch actually requested. */
function requestedUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return (fetchMock.mock.calls[0][0] as Request).url;
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
  localStorage.setItem(API_KEY_STORAGE_KEY, "test-key");
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("rules module", () => {
  it("returns parsed data on success", async () => {
    stubFetch(200, [{ id: 1, name: "Morning check" }]);

    const rules = await getRules();

    expect(rules).toEqual([{ id: 1, name: "Morning check" }]);
  });

  it("builds the path from typed params", async () => {
    const fetchMock = stubFetch(200, { id: 7 });

    await getRule(7);

    expect(requestedUrl(fetchMock)).toContain("/api/v1/rules/7");
  });

  it("throws ApiError carrying the status on failure", async () => {
    stubFetch(404, { detail: "Rule 99 not found" });

    const error = await captureApiError(getRule(99));

    expect(error.status).toBe(404);
    expect(error.message).toBe("Rule 99 not found");
  });

  it("returns null for 204 responses, as the old client did", async () => {
    stubFetch(204, null);

    await expect(deleteRule(3)).resolves.toBeNull();
  });

  it("sends the request body as JSON", async () => {
    const fetchMock = stubFetch(200, []);

    await replaceRuleEdges(4, [
      { source_step_id: 1, source_port: "main", target_step_id: 2, target_port: "main" },
    ]);

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("PUT");
    expect(await request.json()).toEqual({
      edges: [{ source_step_id: 1, source_port: "main", target_step_id: 2, target_port: "main" }],
    });
  });

  it("POSTs an execute with no body", async () => {
    const fetchMock = stubFetch(202, { execution_id: 12, status: "running" });

    const out = await executeRule(5);

    expect(out).toEqual({ execution_id: 12, status: "running" });
    expect((fetchMock.mock.calls[0][0] as Request).method).toBe("POST");
  });
});

describe("query serialization", () => {
  it("encodes query params rather than interpolating them", async () => {
    // `room_name` is the interesting one: a space and an ampersand are exactly what the old
    // string-interpolating builders got wrong.
    const fetchMock = stubFetch(200, { url: "x" });

    await getSampleImage({ source_type: "camera", room_name: "Front Room & Hall" });

    const url = requestedUrl(fetchMock);
    expect(url).toContain("source_type=camera");
    expect(url).toContain("room_name=Front%20Room%20%26%20Hall");
    // The raw value must never reach the URL unescaped.
    expect(url).not.toContain("Front Room & Hall");
  });

  it("omits the query string entirely when no params are given", async () => {
    const fetchMock = stubFetch(200, []);

    await getPipelineRuns();

    expect(requestedUrl(fetchMock)).toMatch(/\/api\/v1\/pipeline\/runs$/);
  });

  it("passes through only the params it is given", async () => {
    const fetchMock = stubFetch(200, []);

    await getWorkflows({ status: "running", limit: 10 });

    const url = requestedUrl(fetchMock);
    expect(url).toContain("status=running");
    expect(url).toContain("limit=10");
    expect(url).not.toContain("rule_id");
  });
});
