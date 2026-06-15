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
  useAggregatorState,
} from "@/composables/useAggregatorState.js";

function mountComposable() {
  let result;
  const wrapper = mount(defineComponent({
    setup() {
      result = useAggregatorState();
      return () => null;
    },
  }));
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
    const { result } = mountComposable();
    for (let depth = 0; depth < AGGREGATOR_HISTORY_LIMIT + 5; depth += 1) {
      mocks.getAggregatorState.mockResolvedValueOnce({ items: [camera(depth)], total: 1 });
      await result.actions.fetch();
    }

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
});
