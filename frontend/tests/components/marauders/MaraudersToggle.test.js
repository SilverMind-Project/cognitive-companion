import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { reactive } from "vue";

// Mock useMaraudersMode so the toggle is a pure presentational test.
// The composable's singleton logic is already tested in useMaraudersMode.spec.js.
const mockState = reactive({ enabled: false, reducedMotion: false });
const mockActions = { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() };

vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({ state: mockState, actions: mockActions }),
}));

import MaraudersToggle from "@/components/marauders/MaraudersToggle.vue";

const stubs = {
  "v-btn": {
    props: ["icon", "color", "variant", "size", "title", "aria-label"],
    emits: ["click"],
    template: `<button
      :data-icon="icon"
      :data-color="color"
      :title="title"
      :aria-label="ariaLabel"
      @click="$emit('click')"
    ><slot /></button>`,
  },
};

function mountToggle() {
  return mount(MaraudersToggle, { global: { stubs } });
}

describe("MaraudersToggle", () => {
  beforeEach(() => {
    mockState.enabled = false;
    vi.clearAllMocks();
  });

  it("shows the scroll/script icon when marauders mode is disabled", () => {
    const wrapper = mountToggle();
    expect(wrapper.find("button").attributes("data-icon")).toBe("mdi-script-outline");
  });

  it("shows the map-marker-path icon when marauders mode is enabled", () => {
    mockState.enabled = true;
    const wrapper = mountToggle();
    expect(wrapper.find("button").attributes("data-icon")).toBe("mdi-map-marker-path");
  });

  it("applies primary color when enabled, none when disabled", () => {
    mockState.enabled = true;
    const enabled = mountToggle();
    expect(enabled.find("button").attributes("data-color")).toBe("primary");

    mockState.enabled = false;
    const disabled = mountToggle();
    expect(disabled.find("button").attributes("data-color")).toBeUndefined();
  });

  it("calls actions.toggle() on click", async () => {
    const wrapper = mountToggle();
    await wrapper.find("button").trigger("click");
    expect(mockActions.toggle).toHaveBeenCalledTimes(1);
  });

  it("has an accessible label (title and aria-label attributes)", () => {
    const wrapper = mountToggle();
    const btn = wrapper.find("button");
    expect(btn.attributes("title")).toBeTruthy();
    expect(btn.attributes("aria-label")).toBeTruthy();
    expect(btn.attributes("aria-label")).toContain("Marauder");
  });

  it("accessible label changes when enabled state changes", async () => {
    const wrapper = mountToggle();
    const labelOff = wrapper.find("button").attributes("aria-label");

    mockState.enabled = true;
    await wrapper.vm.$nextTick();
    const labelOn = wrapper.find("button").attributes("aria-label");

    expect(labelOff).not.toBe(labelOn);
    expect(labelOn).toContain("Disable");
    expect(labelOff).toContain("Enable");
  });
});
