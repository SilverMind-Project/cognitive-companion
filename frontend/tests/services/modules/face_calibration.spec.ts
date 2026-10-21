import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { API_KEY_STORAGE_KEY } from "@/services/http";
import {
  deleteCalibrationCandidate,
  getFaceCalibrationSummary,
  labelCalibrationCandidate,
  listCalibrationCandidates,
  rejectCalibrationCandidate,
} from "@/services/modules/face_calibration";

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function request(fetchMock: ReturnType<typeof vi.fn>): Request {
  return fetchMock.mock.calls[0][0] as Request;
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(API_KEY_STORAGE_KEY, "test-key");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("face calibration module", () => {
  it("lists a state with paging", async () => {
    const fetchMock = stubFetch(200, { candidates: [], next_cursor: null });
    await listCalibrationCandidates("unlabeled", "cursor-1", 20);
    const url = new URL(request(fetchMock).url);
    expect(url.pathname).toBe("/api/v1/face-calibration/candidates");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      state: "unlabeled",
      limit: "20",
      cursor: "cursor-1",
    });
  });

  it("posts a label body without any labeler field", async () => {
    const fetchMock = stubFetch(200, {});
    await labelCalibrationCandidate("c/1", { label_kind: "member", label_identity_id: "amma" });
    const req = request(fetchMock);
    expect(new URL(req.url).pathname).toBe("/api/v1/face-calibration/candidates/c%2F1/label");
    expect(await req.json()).toEqual({ label_kind: "member", label_identity_id: "amma" });
  });

  it("rejects, deletes, and reads the summary on their own paths", async () => {
    let fetchMock = stubFetch(200, {});
    await rejectCalibrationCandidate("c1");
    expect(request(fetchMock).method).toBe("POST");
    expect(new URL(request(fetchMock).url).pathname).toBe(
      "/api/v1/face-calibration/candidates/c1/reject",
    );
    fetchMock = stubFetch(204, null);
    await deleteCalibrationCandidate("c1");
    expect(request(fetchMock).method).toBe("DELETE");
    fetchMock = stubFetch(200, { identities: [] });
    await getFaceCalibrationSummary();
    expect(new URL(request(fetchMock).url).pathname).toBe("/api/v1/face-calibration/summary");
  });
});
