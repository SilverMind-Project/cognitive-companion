import { describe, expect, it, vi } from "vitest";
import { useDailyLivingHealth } from "@/composables/useDailyLivingHealth.js";
import { getDailyLivingHealth } from "@/services/modules/admin";

vi.mock("@/services/modules/admin", () => ({
  getDailyLivingHealth: vi.fn(),
}));

describe("useDailyLivingHealth", () => {
  it("returns { state, actions } shape", () => {
    const composable = useDailyLivingHealth();

    expect(composable).toHaveProperty("state");
    expect(composable).toHaveProperty("actions");
    expect(composable.state).toHaveProperty("loading");
    expect(composable.state).toHaveProperty("error");
    expect(composable.state).toHaveProperty("health");
    expect(composable.actions).toHaveProperty("refresh");
  });

  it("transitions loading -> loaded on a successful refresh", async () => {
    const payload = {
      semantic_memory: {
        reachable: true,
        last_observation_at: "2026-07-21T14:00:00Z",
        last_movement_at: null,
        observations_by_day: [],
        total_observations: 3,
        total_movements: 0,
        stale: false,
      },
      activity_ledger: { by_type: [], stale: true },
    };
    getDailyLivingHealth.mockResolvedValue(payload);
    const { state, actions } = useDailyLivingHealth();

    const promise = actions.refresh();
    expect(state.loading).toBe(true);
    await promise;

    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.health).toEqual(payload);
  });

  it("sets error and clears health on a failed refresh", async () => {
    getDailyLivingHealth.mockRejectedValue(new Error("upstream unavailable"));
    const { state, actions } = useDailyLivingHealth();

    await actions.refresh();

    expect(state.loading).toBe(false);
    expect(state.error).toBe("upstream unavailable");
    expect(state.health).toBeNull();
  });
});
