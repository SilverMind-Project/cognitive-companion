import { describe, it, expect, vi, beforeEach } from "vitest";
import { ctsIdentity, CorrectionError } from "@/services/cts_identity.js";

function mockFetch(status, body) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

describe("cts_identity service", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("proposes a segment via POST", async () => {
    global.fetch = mockFetch(200, {
      ph_id: "ph-1",
      observation_ids: ["o1"],
      start: {},
      end: {},
      ph_version: 2,
    });
    const out = await ctsIdentity.propose({ ph_id: "ph-1" });
    expect(out.ph_version).toBe(2);
    const [url, opts] = global.fetch.mock.calls[0];
    expect(url).toContain("/identity/corrections/propose");
    expect(opts.method).toBe("POST");
  });

  it("raises a CorrectionError carrying status and code", async () => {
    global.fetch = mockFetch(409, {
      detail: { code: "correction.stale_version", message: "stale" },
    });
    await expect(ctsIdentity.apply({ ph_id: "ph-1" })).rejects.toMatchObject({
      status: 409,
      code: "correction.stale_version",
    });
  });

  it("exposes isStale on a 409 stale-version error", async () => {
    const err = new CorrectionError("stale", {
      status: 409,
      code: "correction.stale_version",
    });
    expect(err.isStale).toBe(true);
    expect(new CorrectionError("x", { status: 422, code: "other" }).isStale).toBe(false);
  });

  it("fetches job status", async () => {
    global.fetch = mockFetch(200, {
      revision_id: "r1",
      status: "completed",
      required_projections: ["cc"],
      row_counts: { cc: 2 },
      attempts: 1,
    });
    const job = await ctsIdentity.job("r1");
    expect(job.status).toBe("completed");
    expect(global.fetch.mock.calls[0][0]).toContain("/identity/corrections/jobs/r1");
  });
});
