import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent } from "vue";
import { mount } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  getAggregatorState: vi.fn(),
}));

vi.mock("@/services/api.js", () => ({
  api: {
    getAggregatorState: (...args) => mocks.getAggregatorState(...args),
  },
}));

import {
  AGGREGATOR_HISTORY_LIMIT,
  AGGREGATOR_SAMPLE_SECONDS,
  useAggregatorState,
} from "@/composables/useAggregatorState.js";
import { formatDateTimeShort } from "@/services/timezone.js";

function mountComposable() {
  let result;
  const wrapper = mount(
    defineComponent({
      setup() {
        result = useAggregatorState();
        return () => null;
      },
    }),
  );
  return { result, wrapper };
}

function camera(depth = 3) {
  return {
    camera_id: "camera-1",
    origin: "cts",
    display_name: "Hallway",
    room_name: "Hall",
    buffer_depth: depth,
    buffer_capacity: 20,
    pending_flush: null,
    cooldown_remaining_seconds: null,
    rate_per_second: 1,
    tokens_available: 1,
    images_eligible_total: 10,
    images_dropped_total: 2,
    last_event_at: "2026-06-14T12:00:00Z",
  };
}

beforeEach(() => {
  mocks.getAggregatorState.mockReset();
  mocks.getAggregatorState.mockResolvedValue({ items: [camera()], total: 1 });
});

describe("useAggregatorState", () => {
  it("fetch populates items and total", async () => {
    const { result } = mountComposable();

    await result.actions.fetch();

    expect(result.state.items).toEqual([camera()]);
    expect(result.state.total).toBe(1);
    expect(mocks.getAggregatorState).toHaveBeenCalledWith({ limit: 25, offset: 0 });
  });

  it("onPageOptions resets page when itemsPerPage changes", async () => {
    const { result } = mountComposable();
    result.state.page = 4;

    await result.actions.onPageOptions({ page: 4, itemsPerPage: 50 });

    expect(result.state.page).toBe(1);
    expect(result.state.itemsPerPage).toBe(50);
    expect(mocks.getAggregatorState).toHaveBeenLastCalledWith({ limit: 50, offset: 0 });
  });

  it("setFilter resets page and refetches with the filter", async () => {
    const { result } = mountComposable();
    result.state.page = 3;

    await result.actions.setFilter("origin", "cts");

    expect(result.state.page).toBe(1);
    expect(mocks.getAggregatorState).toHaveBeenLastCalledWith({
      origin: "cts",
      limit: 25,
      offset: 0,
    });
  });

  it("caps camera depth history at the configured ring size", async () => {
    vi.useFakeTimers();
    const { result } = mountComposable();
    for (let depth = 0; depth < AGGREGATOR_HISTORY_LIMIT + 5; depth += 1) {
      mocks.getAggregatorState.mockResolvedValueOnce({ items: [camera(depth)], total: 1 });
      await result.actions.fetch();
      vi.advanceTimersByTime(AGGREGATOR_SAMPLE_SECONDS * 1000);
    }
    vi.useRealTimers();

    const history = result.state.history.get("camera-1");
    expect(history).toHaveLength(AGGREGATOR_HISTORY_LIMIT);
    expect(history[0].depth).toBe(5);
    expect(history.at(-1).depth).toBe(AGGREGATOR_HISTORY_LIMIT + 4);
  });

  it("sets error state when the API fails", async () => {
    const { result } = mountComposable();
    mocks.getAggregatorState.mockRejectedValueOnce(new Error("Unavailable"));

    await result.actions.fetch();

    expect(result.state.error).toBe("Unavailable");
    expect(result.state.items).toEqual([]);
  });

  it("clears the auto-refresh interval on unmount", async () => {
    vi.useFakeTimers();
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");
    const { result, wrapper } = mountComposable();

    result.state.autoRefresh = true;
    await wrapper.vm.$nextTick();
    wrapper.unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
    clearIntervalSpy.mockRestore();
    vi.useRealTimers();
  });

  it("stamps history points with ISO times the timezone formatters accept", async () => {
    const { result } = mountComposable();

    await result.actions.fetch();

    const [point] = result.state.history.get("camera-1");
    expect(typeof point.t).toBe("string");
    expect(Number.isNaN(Date.parse(point.t))).toBe(false);
    expect(() => formatDateTimeShort(point.t)).not.toThrow();
  });

  it("sampleCamera appends one camera's depth without replacing the table rows", async () => {
    vi.useFakeTimers();
    const { result } = mountComposable();
    await result.actions.fetch();
    vi.advanceTimersByTime(AGGREGATOR_SAMPLE_SECONDS * 1000);
    mocks.getAggregatorState.mockResolvedValueOnce({ items: [camera(9)], total: 1 });

    await result.actions.sampleCamera("camera-1");
    vi.useRealTimers();

    expect(mocks.getAggregatorState).toHaveBeenLastCalledWith({ camera_id: "camera-1", limit: 1 });
    expect(result.state.items).toEqual([camera()]);
    expect(result.state.history.get("camera-1").map((p) => p.depth)).toEqual([3, 9]);
  });

  it("samples on its own cadence until stopped, and stops on unmount", async () => {
    vi.useFakeTimers();
    const { result, wrapper } = mountComposable();

    result.actions.startSampling("camera-1");
    expect(mocks.getAggregatorState).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(AGGREGATOR_SAMPLE_SECONDS * 1000 * 2);
    expect(mocks.getAggregatorState).toHaveBeenCalledTimes(3);

    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(AGGREGATOR_SAMPLE_SECONDS * 1000 * 2);
    expect(mocks.getAggregatorState).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });

  it("waits one period before sampling a camera the table fetch just recorded", async () => {
    vi.useFakeTimers();
    const { result, wrapper } = mountComposable();
    await result.actions.fetch();
    mocks.getAggregatorState.mockClear();

    result.actions.startSampling("camera-1");
    expect(mocks.getAggregatorState).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(AGGREGATOR_SAMPLE_SECONDS * 1000);
    expect(mocks.getAggregatorState).toHaveBeenCalledTimes(1);

    wrapper.unmount();
    vi.useRealTimers();
  });

  it("collapses samples taken within a second into the latest one", async () => {
    const { result } = mountComposable();
    await result.actions.fetch();
    mocks.getAggregatorState.mockResolvedValueOnce({ items: [camera(7)], total: 1 });
    await result.actions.fetch();

    expect(result.state.history.get("camera-1").map((p) => p.depth)).toEqual([7]);
  });
});
