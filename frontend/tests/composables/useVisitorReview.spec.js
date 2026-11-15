import { describe, it, expect, vi, beforeEach } from "vitest";

const mockModule = vi.hoisted(() => ({
  listVisitorClusters: vi.fn(),
  getVisitorCluster: vi.fn(),
  nameVisitorCluster: vi.fn(),
  reviewVisitorClusters: vi.fn(),
  mergeVisitorClusters: vi.fn(),
}));

vi.mock("@/services/modules/visitors", () => mockModule);

const targetsApi = vi.hoisted(() => ({
  getIdentityTargets: vi.fn().mockResolvedValue({
    targets: [],
    enrollment_available: true,
    gallery_available: true,
  }),
}));
vi.mock("@/services/modules/identity_targets", () => targetsApi);

vi.mock("@/services/http", () => {
  class ApiError extends Error {
    constructor(status, detail) {
      super(typeof detail === "string" ? detail : `HTTP ${status}`);
      this.status = status;
      this.detail = detail;
    }
  }
  return { ApiError };
});

import { useVisitorReview } from "@/composables/useVisitorReview.js";
import { ApiError } from "@/services/http";

const notify = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };

function cluster(id, overrides = {}) {
  return {
    cluster_id: id,
    status: "surfaced",
    sighting_count: 3,
    distinct_days: 3,
    first_seen_at: "2026-07-01T10:00:00Z",
    last_seen_at: "2026-07-19T10:00:00Z",
    recent_crop_urls: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useVisitorReview", () => {
  it("loads the cluster list", async () => {
    mockModule.listVisitorClusters.mockResolvedValue({ clusters: [cluster("c1")], total: 1 });
    const { state, actions } = useVisitorReview(notify);

    await actions.loadList();

    expect(state.clusters).toHaveLength(1);
    expect(state.total).toBe(1);
    expect(mockModule.listVisitorClusters).toHaveBeenCalledWith("surfaced");
  });

  it("setStatusFilter changes the filter and reloads", async () => {
    mockModule.listVisitorClusters.mockResolvedValue({ clusters: [], total: 0 });
    const { state, actions } = useVisitorReview(notify);

    await actions.setStatusFilter("candidate");

    expect(state.statusFilter).toBe("candidate");
    expect(mockModule.listVisitorClusters).toHaveBeenCalledWith("candidate");
  });

  it("surfaces a list error without throwing past the caller's catch", async () => {
    mockModule.listVisitorClusters.mockRejectedValue(new ApiError(403, "Insufficient permissions"));
    const { state, actions } = useVisitorReview(notify);

    await expect(actions.loadList()).rejects.toThrow();

    expect(state.listError).toBe("Insufficient permissions");
  });

  it("nameCluster sends person_id/name and refreshes the list on success", async () => {
    mockModule.nameVisitorCluster.mockResolvedValue({
      cluster_id: "c1",
      named_person_id: "nurse-priya",
    });
    mockModule.listVisitorClusters.mockResolvedValue({ clusters: [], total: 0 });
    const { actions } = useVisitorReview(notify);

    await actions.nameCluster("c1", { personId: "nurse-priya", name: "Nurse Priya" });

    expect(mockModule.nameVisitorCluster).toHaveBeenCalledWith("c1", {
      person_id: "nurse-priya",
      name: "Nurse Priya",
    });
    expect(notify.success).toHaveBeenCalled();
    // The new member must appear in every picker without a reload.
    expect(targetsApi.getIdentityTargets).toHaveBeenCalledTimes(1);
  });

  it("review sends one batch and shows the server's effect", async () => {
    mockModule.reviewVisitorClusters.mockResolvedValue({
      results: [
        { id: "c1", ok: true, error_code: null },
        { id: "c2", ok: true, error_code: null },
      ],
      reviewed: 2,
      failed: 0,
      effect: "Marked as faces of Resident.",
    });
    mockModule.listVisitorClusters.mockResolvedValue({ clusters: [], total: 0 });
    const { state, actions } = useVisitorReview(notify);
    actions.toggleSelection("c1");
    actions.toggleSelection("c2");
    actions.toggleSelection("c3");

    await actions.review(["c1", "c2"], "is_member", "resident");

    expect(mockModule.reviewVisitorClusters).toHaveBeenCalledWith({
      cluster_ids: ["c1", "c2"],
      verdict: "is_member",
      target_identity_id: "resident",
    });
    expect(notify.success).toHaveBeenCalledWith("Marked as faces of Resident.");
    // Reviewed clusters leave the selection; the rest stay selected.
    expect(state.selection).toEqual(["c3"]);
    expect(mockModule.listVisitorClusters).toHaveBeenCalled();
  });

  it("review without a target omits it and reports partial failures by reason", async () => {
    mockModule.reviewVisitorClusters.mockResolvedValue({
      results: [
        { id: "c1", ok: true, error_code: null },
        { id: "c2", ok: false, error_code: "already_named" },
        { id: "c3", ok: false, error_code: "already_named" },
      ],
      reviewed: 1,
      failed: 2,
      effect: "Dismissed.",
    });
    mockModule.listVisitorClusters.mockResolvedValue({ clusters: [], total: 0 });
    const { actions } = useVisitorReview(notify);

    await actions.review(["c1", "c2", "c3"], "not_usable");

    expect(mockModule.reviewVisitorClusters).toHaveBeenCalledWith({
      cluster_ids: ["c1", "c2", "c3"],
      verdict: "not_usable",
    });
    expect(notify.warning).toHaveBeenCalledWith("2 not updated: is already named.");
  });

  it("a 409 during a mutation sets the disabled flag and warns instead of erroring", async () => {
    mockModule.reviewVisitorClusters.mockRejectedValue(
      new ApiError(409, "Visitor clustering is disabled"),
    );
    const { state, actions } = useVisitorReview(notify);

    await expect(actions.review(["c1"], "not_usable")).rejects.toThrow();

    expect(state.disabled).toBe(true);
    expect(notify.warning).toHaveBeenCalled();
    expect(notify.error).not.toHaveBeenCalled();
  });

  describe("selection", () => {
    it("keeps every selected cluster for a batch decision", () => {
      const { state, actions } = useVisitorReview(notify);

      actions.toggleSelection("c1");
      actions.toggleSelection("c2");
      actions.toggleSelection("c3");

      expect(state.selection).toEqual(["c1", "c2", "c3"]);
    });

    it("toggling an already-selected cluster removes it", () => {
      const { state, actions } = useVisitorReview(notify);

      actions.toggleSelection("c1");
      actions.toggleSelection("c1");

      expect(state.selection).toEqual([]);
    });

    it("mergeSelected merges the two selected clusters and clears the selection", async () => {
      mockModule.mergeVisitorClusters.mockResolvedValue({ cluster_id: "c1", status: "candidate" });
      mockModule.listVisitorClusters.mockResolvedValue({ clusters: [], total: 0 });
      const { state, actions } = useVisitorReview(notify);
      actions.toggleSelection("c1");
      actions.toggleSelection("c2");

      await actions.mergeSelected();

      expect(mockModule.mergeVisitorClusters).toHaveBeenCalledWith("c1", "c2");
      expect(state.selection).toEqual([]);
    });
  });
});
