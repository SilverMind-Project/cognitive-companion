import { describe, expect, it, vi } from "vitest";
import { useGuidedMetrics } from "@/composables/useGuidedMetrics.js";
import { api } from "@/services/api.js";

vi.mock("@/services/api.js", () => ({
  api: {
    getRoutine: vi.fn(),
    getGuidedMetricsDashboard: vi.fn(),
  },
}));

describe("useGuidedMetrics", () => {
  it("returns { state, actions } shape", () => {
    const composable = useGuidedMetrics();

    expect(composable).toHaveProperty("state");
    expect(composable).toHaveProperty("actions");
    expect(composable.state).toHaveProperty("dashboard");
    expect(composable.state).toHaveProperty("loading");
    expect(composable.actions).toHaveProperty("fetchDashboard");
    expect(composable).not.toHaveProperty("dashboard");
  });

  it("fetches routine first and then server-side dashboard metrics", async () => {
    api.getRoutine.mockResolvedValue({
      routine: { id: 7, person_id: "resident-1", name: "Make tea" },
      steps: [],
    });
    api.getGuidedMetricsDashboard.mockResolvedValue({
      completion: { completion_rate: 1 },
    });
    const { state, actions } = useGuidedMetrics();

    await actions.fetchDashboard("7");

    expect(api.getRoutine).toHaveBeenCalledWith("7");
    expect(api.getGuidedMetricsDashboard).toHaveBeenCalledWith({
      person_id: "resident-1",
      routine_id: 7,
    });
    expect(state.routine.name).toBe("Make tea");
    expect(state.dashboard.completion.completion_rate).toBe(1);
  });
});
