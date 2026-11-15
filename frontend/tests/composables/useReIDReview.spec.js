import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockSvc, mockIdentity } = vi.hoisted(() => ({
  mockSvc: {
    list: vi.fn(),
    detail: vi.fn(),
    events: vi.fn(),
    counts: vi.fn(),
    approve: vi.fn(),
    relabel: vi.fn(),
    demote: vi.fn(),
    reject: vi.fn(),
    reviewBatch: vi.fn(),
    compensate: vi.fn(),
  },
  mockIdentity: { getIdentityTargets: vi.fn() },
}));

vi.mock("@/services/modules/identity_targets", () => mockIdentity);

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
  return { ctsReidReview: mockSvc, CorrectionError };
});

import { useReIDReview } from "@/composables/useReIDReview.js";
import { CorrectionError } from "@/services/cts_identity";

const notify = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

beforeEach(() => {
  vi.clearAllMocks();
  mockSvc.counts.mockResolvedValue({
    pending_review: 3,
    auto_verified: 0,
    operator_verified: 1,
    rejected: 2,
  });
  mockIdentity.getIdentityTargets.mockResolvedValue({
    targets: [{ identity_id: "amma", display_name: "Amma" }],
    enrollment_available: true,
    gallery_available: true,
  });
});

function candidate(id, version = 1, state = "pending_review") {
  return { candidate_id: id, audit_version: version, state };
}

describe("useReIDReview", () => {
  it("loads the list and clears stale selections", async () => {
    mockSvc.list.mockResolvedValue({
      candidates: [candidate("c1"), candidate("c2")],
      total: 2,
      limit: 25,
      offset: 0,
    });
    const { state, actions } = useReIDReview(notify);
    await actions.loadList();
    expect(state.candidates.value).toHaveLength(2);
    actions.toggleSelected("c1");
    expect(state.selectedIds.value).toEqual(["c1"]);

    // A reload that no longer contains c1 drops it from the selection.
    mockSvc.list.mockResolvedValue({
      candidates: [candidate("c2")],
      total: 1,
      limit: 25,
      offset: 0,
    });
    await actions.loadList();
    expect(state.selectedIds.value).toEqual([]);
  });

  it("setFilter resets to the first page", async () => {
    mockSvc.list.mockResolvedValue({ candidates: [], total: 0, limit: 25, offset: 0 });
    const { state, actions } = useReIDReview(notify);
    state.offset.value = 50;
    await actions.setFilter("camera_id", "kitchen-1");
    expect(state.offset.value).toBe(0);
    expect(state.filters.value.camera_id).toBe("kitchen-1");
  });

  it("a stale earlier list response cannot overwrite a newer one", async () => {
    const { state, actions } = useReIDReview(notify);
    let resolveSlow;
    mockSvc.list
      .mockReturnValueOnce(new Promise((r) => (resolveSlow = r)))
      .mockResolvedValueOnce({ candidates: [candidate("new")], total: 1, limit: 25, offset: 0 });
    const slow = actions.loadList();
    const fast = actions.loadList();
    await fast;
    resolveSlow({ candidates: [candidate("old")], total: 1, limit: 25, offset: 0 });
    await slow;
    expect(state.candidates.value[0].candidate_id).toBe("new");
  });

  it("approve passes the base audit version and refreshes via invalidate", async () => {
    mockSvc.list.mockResolvedValue({
      candidates: [candidate("c1", 4)],
      total: 1,
      limit: 25,
      offset: 0,
    });
    mockSvc.approve.mockResolvedValue(candidate("c1", 5, "operator_verified"));
    const { actions } = useReIDReview(notify);
    await actions.loadList();
    await actions.approve("c1");
    expect(mockSvc.approve).toHaveBeenCalledWith("c1", { base_audit_version: 4, note: null });
    // invalidate re-lists and re-counts.
    expect(mockSvc.counts).toHaveBeenCalled();
  });

  it("a 409 on a mutation refreshes state and warns, not a generic error", async () => {
    mockSvc.list.mockResolvedValue({
      candidates: [candidate("c1", 1)],
      total: 1,
      limit: 25,
      offset: 0,
    });
    mockSvc.approve.mockRejectedValue(
      new CorrectionError("stale", { status: 409, code: "reid_review.stale" }),
    );
    const { actions } = useReIDReview(notify);
    await actions.loadList();
    await expect(actions.approve("c1")).rejects.toBeInstanceOf(CorrectionError);
    expect(notify.warning).toHaveBeenCalled();
    expect(notify.error).not.toHaveBeenCalled();
  });

  it("loads household targets independent of gallery population", async () => {
    const { state, actions } = useReIDReview(notify);
    await actions.loadTargets();
    expect(mockIdentity.getIdentityTargets).toHaveBeenCalledTimes(1);
    // Opening the page again refetches, so a member added elsewhere appears.
    await useReIDReview(notify).actions.loadTargets();
    expect(mockIdentity.getIdentityTargets).toHaveBeenCalledTimes(2);
    expect(state.targets.value).toEqual([{ identity_id: "amma", display_name: "Amma" }]);
  });

  it("relabel sends the household target identity and base version", async () => {
    mockSvc.list.mockResolvedValue({
      candidates: [candidate("c1", 7)],
      total: 1,
      limit: 25,
      offset: 0,
    });
    mockSvc.relabel.mockResolvedValue(candidate("c1", 8, "operator_verified"));
    const { actions } = useReIDReview(notify);
    await actions.loadList();
    await actions.relabel("c1", { target_identity_id: "amma" });
    expect(mockSvc.relabel).toHaveBeenCalledWith("c1", {
      base_audit_version: 7,
      target_identity_id: "amma",
      note: null,
    });
  });

  it("demote passes the base audit version and refreshes via invalidate", async () => {
    mockSvc.list.mockResolvedValue({
      candidates: [candidate("c1", 3, "auto_verified")],
      total: 1,
      limit: 25,
      offset: 0,
    });
    mockSvc.demote.mockResolvedValue(candidate("c1", 4, "pending_review"));
    const { actions } = useReIDReview(notify);
    await actions.loadList();
    await actions.demote("c1");
    expect(mockSvc.demote).toHaveBeenCalledWith("c1", { base_audit_version: 3, note: null });
    expect(mockSvc.counts).toHaveBeenCalled();
  });

  it("reviewSelected sends one batch, states the effect, and keeps what did not apply", async () => {
    mockSvc.list.mockResolvedValue({
      candidates: [candidate("c1", 2), candidate("c2", 3)],
      total: 2,
      limit: 25,
      offset: 0,
    });
    mockSvc.reviewBatch.mockResolvedValue({
      results: [
        { id: "c1", ok: true, error_code: null },
        { id: "c2", ok: false, error_code: "conflict" },
      ],
      reviewed: 1,
      failed: 1,
      effect: "Rejected as the wrong person.",
    });
    const { state, actions } = useReIDReview(notify);
    await actions.loadList();
    actions.toggleSelected("c1");
    actions.toggleSelected("c2");
    await actions.reviewSelected({ verdict: "not_enrolled" });
    const arg = mockSvc.reviewBatch.mock.calls[0][0];
    expect(arg.verdict).toBe("not_enrolled");
    expect(arg.items).toEqual([
      { candidate_id: "c1", base_audit_version: 2 },
      { candidate_id: "c2", base_audit_version: 3 },
    ]);
    expect(notify.success).toHaveBeenCalledWith("Rejected as the wrong person.");
    expect(notify.warning).toHaveBeenCalledWith("1 not updated: changed since it was loaded.");
    expect(state.selectedIds.value).toEqual(["c2"]);
  });

  it("records a counts failure instead of passing placeholder zeros off as real", async () => {
    mockSvc.counts.mockRejectedValueOnce(new Error("upstream down"));
    const { state, actions } = useReIDReview(notify);
    expect(state.countsLoaded.value).toBe(false);

    await actions.loadCounts();
    expect(state.countsLoaded.value).toBe(false);
    expect(state.countsError.value).toBe("upstream down");

    await actions.loadCounts();
    expect(state.countsLoaded.value).toBe(true);
    expect(state.countsError.value).toBe("");
    expect(state.counts.value.pending_review).toBe(3);
  });
});
