import { describe, it, expect, vi, beforeEach } from "vitest";

const mockModule = vi.hoisted(() => ({
  listVisitorClusters: vi.fn(),
  getVisitorCluster: vi.fn(),
  nameVisitorCluster: vi.fn(),
  dismissVisitorCluster: vi.fn(),
  mergeVisitorClusters: vi.fn(),
}));

vi.mock("@/services/modules/visitors", () => mockModule);

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
  });

  it("dismissCluster calls the module and refreshes", async () => {
    mockModule.dismissVisitorCluster.mockResolvedValue({ cluster_id: "c1", status: "dismissed" });
    mockModule.listVisitorClusters.mockResolvedValue({ clusters: [], total: 0 });
    const { actions } = useVisitorReview(notify);

    await actions.dismissCluster("c1");

    expect(mockModule.dismissVisitorCluster).toHaveBeenCalledWith("c1");
  });

  it("a 409 during a mutation sets the disabled flag and warns instead of erroring", async () => {
    mockModule.dismissVisitorCluster.mockRejectedValue(
      new ApiError(409, "Visitor clustering is disabled"),
    );
    const { state, actions } = useVisitorReview(notify);

    await expect(actions.dismissCluster("c1")).rejects.toThrow();

    expect(state.disabled).toBe(true);
    expect(notify.warning).toHaveBeenCalled();
    expect(notify.error).not.toHaveBeenCalled();
  });

  describe("merge selection", () => {
    it("tracks up to two selected clusters, dropping the oldest on a third", () => {
      const { state, actions } = useVisitorReview(notify);

      actions.toggleMergeSelection("c1");
      actions.toggleMergeSelection("c2");
      actions.toggleMergeSelection("c3");

      expect(state.mergeSelection).toEqual(["c2", "c3"]);
    });

    it("toggling an already-selected cluster removes it", () => {
      const { state, actions } = useVisitorReview(notify);

      actions.toggleMergeSelection("c1");
      actions.toggleMergeSelection("c1");

      expect(state.mergeSelection).toEqual([]);
    });

    it("mergeSelected merges the two selected clusters and clears the selection", async () => {
      mockModule.mergeVisitorClusters.mockResolvedValue({ cluster_id: "c1", status: "candidate" });
      mockModule.listVisitorClusters.mockResolvedValue({ clusters: [], total: 0 });
      const { state, actions } = useVisitorReview(notify);
      actions.toggleMergeSelection("c1");
      actions.toggleMergeSelection("c2");

      await actions.mergeSelected();

      expect(mockModule.mergeVisitorClusters).toHaveBeenCalledWith("c1", "c2");
      expect(state.mergeSelection).toEqual([]);
    });
  });
});
