import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockSvc } = vi.hoisted(() => ({
  mockSvc: {
    correctionTargets: vi.fn(),
    propose: vi.fn(),
    apply: vi.fn(),
    compensate: vi.fn(),
    job: vi.fn(),
  },
}));

vi.mock("@/services/cts_identity", () => {
  class CorrectionError extends Error {
    constructor(message, { status = 0, code = "" } = {}) {
      super(message);
      this.status = status;
      this.code = code;
    }
    get isStale() {
      return this.status === 409 && this.code === "correction.stale_version";
    }
  }
  return { ctsIdentity: mockSvc, CorrectionError };
});

import { useIdentityCorrection } from "@/composables/useIdentityCorrection.js";
import { CorrectionError } from "@/services/cts_identity";

const notify = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useIdentityCorrection", () => {
  it("loads correction targets and gallery availability", async () => {
    mockSvc.correctionTargets.mockResolvedValue({
      targets: [{ identity_id: "amma", display_name: "Amma" }],
      gallery_available: false,
    });
    const { state, actions } = useIdentityCorrection(notify);
    await actions.loadTargets();
    expect(state.targets.value).toHaveLength(1);
    expect(state.galleryAvailable.value).toBe(false);
  });

  it("surfaces a targets error for retry", async () => {
    mockSvc.correctionTargets.mockRejectedValue(new Error("boom"));
    const { state, actions } = useIdentityCorrection(notify);
    await expect(actions.loadTargets()).rejects.toThrow();
    expect(state.targetsError.value).toBe("boom");
  });

  it("re-proposes and flags staleConflict on a 409", async () => {
    mockSvc.apply.mockRejectedValue(
      new CorrectionError("stale", { status: 409, code: "correction.stale_version" })
    );
    mockSvc.propose.mockResolvedValue({
      ph_id: "ph-1",
      observation_ids: ["o2"],
      start: { observation_id: "o2", captured_at: "t", reason: "segment_edge" },
      end: { observation_id: "o2", captured_at: "t", reason: "segment_edge" },
      ph_version: 5,
    });
    const { state, actions } = useIdentityCorrection(notify);
    await expect(actions.apply({ ph_id: "ph-1" })).rejects.toBeInstanceOf(CorrectionError);
    expect(state.staleConflict.value).toBe(true);
    expect(mockSvc.propose).toHaveBeenCalledWith({ ph_id: "ph-1", observation_id: null, at: null });
    expect(state.proposal.value.ph_version).toBe(5);
    expect(notify.warning).toHaveBeenCalled();
  });

  it("polls the job until a terminal state", async () => {
    mockSvc.job
      .mockResolvedValueOnce({ revision_id: "r1", status: "applying", required_projections: ["cc"], row_counts: {}, attempts: 0 })
      .mockResolvedValueOnce({ revision_id: "r1", status: "completed", required_projections: ["cc"], row_counts: { cc: 3 }, attempts: 1 });
    const { state, actions } = useIdentityCorrection(notify);
    const job = await actions.pollJob("r1", { intervalMs: 0, maxAttempts: 5 });
    expect(job.status).toBe("completed");
    expect(state.job.value.row_counts).toEqual({ cc: 3 });
    expect(mockSvc.job).toHaveBeenCalledTimes(2);
  });
});
