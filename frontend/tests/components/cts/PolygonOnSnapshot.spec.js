import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { reactive } from "vue";
import PolygonOnSnapshot from "@/components/cts/PolygonOnSnapshot.vue";

const maraudersState = reactive({ enabled: false, reducedMotion: false });

vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({
    state: maraudersState,
    actions: { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() },
  }),
}));

const polygon = [[0.1, 0.1], [0.8, 0.1], [0.5, 0.8]];

function mountPolygon({ isDragging = false } = {}) {
  return mount(PolygonOnSnapshot, {
    props: {
      imageUrl: "/snapshot.jpg",
      imageClass: "cc-floor-plan-background-image",
      modelValue: polygon,
    },
    global: {
      stubs: {
        CcSpatialEditor: {
          name: "CcSpatialEditor",
          props: ["modelValue", "hideInternalPolygon", "imageClass"],
          template: `
            <div data-testid="spatial-editor">
              <slot
                name="overlay"
                :content-rect="{ width: 800, height: 600 }"
                :is-dragging="${isDragging}"
              />
              <polygon v-if="!hideInternalPolygon || ${isDragging}" data-testid="plain-polygon" />
            </div>
          `,
        },
        MaraudersInkPolygon: {
          name: "MaraudersInkPolygon",
          props: ["points", "canvasW", "canvasH", "seedKey"],
          template: "<g data-testid='marauders-ink-polygon' />",
        },
      },
    },
  });
}

beforeEach(() => {
  maraudersState.enabled = false;
});

describe("PolygonOnSnapshot", () => {
  it("forwards the optional image class to the spatial editor", () => {
    const wrapper = mountPolygon();

    expect(wrapper.findComponent({ name: "CcSpatialEditor" }).props("imageClass")).toBe(
      "cc-floor-plan-background-image",
    );
  });

  it("uses the normal internal polygon outside Marauders mode", () => {
    const wrapper = mountPolygon();

    expect(wrapper.findComponent({ name: "CcSpatialEditor" }).props("hideInternalPolygon")).toBe(false);
    expect(wrapper.find("[data-testid='plain-polygon']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='marauders-ink-polygon']").exists()).toBe(false);
  });

  it("uses the ink polygon at rest in Marauders mode", () => {
    maraudersState.enabled = true;
    const wrapper = mountPolygon();

    expect(wrapper.findComponent({ name: "CcSpatialEditor" }).props("hideInternalPolygon")).toBe(true);
    expect(wrapper.find("[data-testid='plain-polygon']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='marauders-ink-polygon']").exists()).toBe(true);
  });

  it("uses the straight polygon during an active vertex drag", () => {
    maraudersState.enabled = true;
    const wrapper = mountPolygon({ isDragging: true });

    expect(wrapper.find("[data-testid='marauders-ink-polygon']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='plain-polygon']").exists()).toBe(true);
  });
});
