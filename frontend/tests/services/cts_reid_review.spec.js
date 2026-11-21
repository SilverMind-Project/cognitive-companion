import { describe, it, expect, vi, beforeEach } from "vitest";
import { ctsReidReview, CorrectionError } from "@/services/cts_identity.js";

function mockFetch(status, body) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

describe("ctsReidReview service", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("lists candidates with query params", async () => {
    global.fetch = mockFetch(200, { candidates: [], total: 0, limit: 25, offset: 0 });
    await ctsReidReview.list({
      state: "pending_review",
      camera_id: "kitchen-1",
      limit: 25,
      offset: 0,
    });
    const [url] = global.fetch.mock.calls[0];
    expect(url).toContain("/identity/reid-review/candidates");
    expect(url).toContain("state=pending_review");
    expect(url).toContain("camera_id=kitchen-1");
  });

  it("omits null/empty query params", async () => {
    global.fetch = mockFetch(200, { candidates: [], total: 0, limit: 25, offset: 0 });
    await ctsReidReview.list({ state: "pending_review", identity_id: null, camera_id: "" });
    const [url] = global.fetch.mock.calls[0];
    expect(url).not.toContain("identity_id");
    expect(url).not.toContain("camera_id");
  });

  it("approves via POST without sending actor", async () => {
    global.fetch = mockFetch(200, { candidate_id: "c1", state: "operator_verified" });
    await ctsReidReview.approve("c1", { base_audit_version: 1, note: "ok" });
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain("/identity/reid-review/candidates/c1/approve");
    expect(opts.method).toBe("POST");
    const body = JSON.parse(opts.body);
    expect(body).not.toHaveProperty("actor");
    expect(body.base_audit_version).toBe(1);
  });

  it("surfaces a 409 stale/ineligible as CorrectionError with status+code", async () => {
    global.fetch = mockFetch(409, {
      detail: { code: "reid_review.ineligible", message: "incompatible_model:v0" },
    });
    await expect(ctsReidReview.approve("c1", { base_audit_version: 1 })).rejects.toMatchObject({
      status: 409,
      code: "reid_review.ineligible",
    });
  });

  it("batch review posts the verdict, reason, and versioned items", async () => {
    global.fetch = mockFetch(200, { results: [], reviewed: 0, failed: 0, effect: "" });
    await ctsReidReview.reviewBatch({
      verdict: "not_usable",
      reason: "low_quality",
      items: [{ candidate_id: "c1", base_audit_version: 1 }],
    });
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain("/identity/reid-review/review");
    expect(JSON.parse(opts.body)).toEqual({
      verdict: "not_usable",
      reason: "low_quality",
      note: null,
      items: [{ candidate_id: "c1", base_audit_version: 1 }],
    });
  });

  it("forwards seed_association_id and expired state filter", async () => {
    global.fetch = mockFetch(200, { candidates: [], total: 0, limit: 25, offset: 0 });
    await ctsReidReview.list({
      state: "expired",
      seed_association_id: "seg-123",
      limit: 25,
      offset: 0,
    });
    const [url] = global.fetch.mock.calls[0];
    expect(url).toContain("state=expired");
    expect(url).toContain("seed_association_id=seg-123");
  });

  it("surfaces a 403 forbidden as CorrectionError", async () => {
    global.fetch = mockFetch(403, { detail: "forbidden" });
    await expect(ctsReidReview.counts()).rejects.toBeInstanceOf(CorrectionError);
    await expect(ctsReidReview.counts()).rejects.toMatchObject({ status: 403 });
  });
});
