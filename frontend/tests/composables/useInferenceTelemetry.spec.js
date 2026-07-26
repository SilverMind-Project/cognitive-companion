import { describe, expect, it, vi } from "vitest";
import { useInferenceTelemetry } from "@/composables/useInferenceTelemetry.js";
import { getInferenceTelemetry } from "@/services/modules/admin";

vi.mock("@/services/modules/admin", () => ({
  getInferenceTelemetry: vi.fn(),
}));

describe("useInferenceTelemetry", () => {
  it("returns { state, actions } shape", () => {
    const composable = useInferenceTelemetry();

    expect(composable).toHaveProperty("state");
    expect(composable).toHaveProperty("actions");
    expect(composable.state).toHaveProperty("loading");
    expect(composable.state).toHaveProperty("error");
    expect(composable.state).toHaveProperty("telemetry");
    expect(composable.actions).toHaveProperty("refresh");
  });

  it("transitions loading -> loaded on a successful refresh", async () => {
    const payload = {
      window_minutes: 60,
      totals_by_caller_lane: [
        { caller: "rule:tea_intent", lane: "vision", ok: 3, timeout: 1, error: 0 },
      ],
      queue_depth: [
        { lane: "vision", depth: 0 },
        { lane: "text", depth: 0 },
      ],
      queue_wait_p50_ms: 10,
      queue_wait_p95_ms: 40,
      timeouts_total: 1,
      calls_per_hour: [],
      ring_buffer_size: 4,
      ring_buffer_capacity: 2000,
    };
    getInferenceTelemetry.mockResolvedValue(payload);
    const { state, actions } = useInferenceTelemetry();

    const promise = actions.refresh();
    expect(state.loading).toBe(true);
    await promise;

    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.telemetry).toEqual(payload);
  });

  it("sets error and clears telemetry on a failed refresh", async () => {
    getInferenceTelemetry.mockRejectedValue(new Error("upstream unavailable"));
    const { state, actions } = useInferenceTelemetry();

    await actions.refresh();

    expect(state.loading).toBe(false);
    expect(state.error).toBe("upstream unavailable");
    expect(state.telemetry).toBeNull();
  });
});
