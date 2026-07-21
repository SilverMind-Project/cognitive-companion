import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { ApiError, API_KEY_STORAGE_KEY } from "@/services/http";
import {
  listVisitorClusters,
  getVisitorCluster,
  nameVisitorCluster,
  dismissVisitorCluster,
  mergeVisitorClusters,
} from "@/services/modules/visitors";

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

function requestedUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return (fetchMock.mock.calls[0][0] as Request).url;
}

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

describe("visitors module", () => {
  it("lists clusters with a status filter", async () => {
    const fetchMock = stubFetch(200, { clusters: [], total: 0 });

    await listVisitorClusters("surfaced");

    expect(requestedUrl(fetchMock)).toContain("/api/v1/visitors/clusters?status=surfaced");
  });

  it("omits the query string when no status is given", async () => {
    const fetchMock = stubFetch(200, { clusters: [], total: 0 });

    await listVisitorClusters();

    expect(requestedUrl(fetchMock)).toMatch(/\/api\/v1\/visitors\/clusters$/);
  });

  it("gets a single cluster by id", async () => {
    const fetchMock = stubFetch(200, { cluster: { cluster_id: "c1" }, recent_sightings: [] });

    await getVisitorCluster("c1");

    expect(requestedUrl(fetchMock)).toContain("/api/v1/visitors/clusters/c1");
  });

  it("names a cluster with the person_id and name body", async () => {
    const fetchMock = stubFetch(200, {
      cluster_id: "c1",
      status: "named",
      named_person_id: "nurse-priya",
      member_name: "Nurse Priya",
      embedding_count: 5,
      household_member_created: true,
    });

    const result = await nameVisitorCluster("c1", {
      person_id: "nurse-priya",
      name: "Nurse Priya",
    });

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("POST");
    expect(request.url).toContain("/api/v1/visitors/clusters/c1/name");
    expect(await request.json()).toEqual({ person_id: "nurse-priya", name: "Nurse Priya" });
    expect(result.named_person_id).toBe("nurse-priya");
  });

  it("surfaces a 409 (disabled clustering) as ApiError with status", async () => {
    stubFetch(409, { detail: "Visitor clustering is disabled" });

    const error = await captureApiError(
      nameVisitorCluster("c1", { person_id: "nurse-priya", name: "Nurse Priya" }),
    );

    expect(error.status).toBe(409);
    expect(error.message).toBe("Visitor clustering is disabled");
  });

  it("dismisses a cluster", async () => {
    const fetchMock = stubFetch(200, { cluster_id: "c1", status: "dismissed" });

    await dismissVisitorCluster("c1");

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("POST");
    expect(request.url).toContain("/api/v1/visitors/clusters/c1/dismiss");
  });

  it("merges two clusters by path params", async () => {
    const fetchMock = stubFetch(200, { cluster_id: "c1", status: "candidate" });

    await mergeVisitorClusters("c1", "c2");

    expect(requestedUrl(fetchMock)).toContain("/api/v1/visitors/clusters/c1/merge/c2");
  });

  it("surfaces a 403 as ApiError", async () => {
    stubFetch(403, { detail: "Insufficient permissions" });

    const error = await captureApiError(listVisitorClusters());

    expect(error.status).toBe(403);
  });
});
