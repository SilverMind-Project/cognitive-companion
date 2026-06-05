import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { reactive } from "vue";

// --- Mocks ------------------------------------------------------------------

const mockGetKeyframeBboxes = vi.fn().mockResolvedValue([]);
const mockApplyBboxBatch = vi.fn().mockResolvedValue({ applied: 0, results: [] });

vi.mock("@/services/cts", () => ({
  cts: {
    getKeyframeBboxes: (...args) => mockGetKeyframeBboxes(...args),
    applyBboxBatch: (...args) => mockApplyBboxBatch(...args),
  },
}));

vi.mock("@/components/common/DialogHeader.vue", () => ({
  default: { template: "<div />", props: ["icon", "label", "title"] },
}));

const maraudersState = reactive({ enabled: false, reducedMotion: false });
vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({
    state: maraudersState,
    actions: { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() },
  }),
}));

vi.mock("@/components/cts/keyframes/BboxCanvas.vue", () => ({
  default: {
    name: "BboxCanvas",
    template: "<div class='mock-bbox-canvas' />",
    props: ["imageUrl", "keyframeId", "initialBboxes", "identities", "maraudersMode"],
    emits: ["bbox-tagged", "bbox-overridden", "bbox-created", "bbox-deleted"],
  },
}));

// Stub Vuetify components.
const stubComponents = {
  "v-btn": { template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div class='v-card'><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-divider": { template: "<hr />" },
  "v-dialog": { template: "<div><slot /></div>", props: ["modelValue"] },
  "v-progress-circular": { template: "<div />" },
  "v-slider": { template: "<input type='range' />" },
};

import KeyframeAnnotationDialog from "../../src/components/cts/keyframes/KeyframeAnnotationDialog.vue";

async function mountDialog() {
  const wrapper = mount(KeyframeAnnotationDialog, {
    props: {
      modelValue: true,
      imageUrl: "https://example.com/frame.jpg",
      keyframeId: "kf-001",
      identities: [],
    },
    global: { stubs: stubComponents },
  });
  await flushPromises();
  return wrapper;
}

describe("KeyframeAnnotationDialog — M3 seam: marauders mode prop", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    maraudersState.enabled = false;
  });

  it("passes marauders-mode=false to BboxCanvas when marauders disabled", async () => {
    const wrapper = await mountDialog();
    const canvas = wrapper.findComponent({ name: "BboxCanvas" });
    expect(canvas.props("maraudersMode")).toBe(false);
  });

  it("passes marauders-mode=true to BboxCanvas when marauders enabled", async () => {
    maraudersState.enabled = true;
    const wrapper = await mountDialog();
    const canvas = wrapper.findComponent({ name: "BboxCanvas" });
    expect(canvas.props("maraudersMode")).toBe(true);
  });
});

describe("KeyframeAnnotationDialog — save handler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("emits error when applyBboxBatch fails", async () => {
    mockApplyBboxBatch.mockRejectedValue(new Error("Server error"));
    const wrapper = await mountDialog();

    // Queue a delete by mutating the reactive array in place.
    const state = wrapper.vm.$.setupState;
    state.pendingDeletes.splice(0, state.pendingDeletes.length, { annotationId: "annot-1" });
    await flushPromises();

    // Click Save Changes button (second button, after Cancel).
    const buttons = wrapper.findAll("button");
    expect(buttons.length).toBeGreaterThanOrEqual(2);
    await buttons[1].trigger("click");
    await flushPromises();

    const errorEvents = wrapper.emitted("error");
    expect(errorEvents).toBeTruthy();
    expect(errorEvents[0][0]).toBe("Server error");
  });

  it("emits saved when applyBboxBatch succeeds", async () => {
    mockApplyBboxBatch.mockResolvedValue({ applied: 1, results: [] });
    mockGetKeyframeBboxes.mockResolvedValue([]);
    const wrapper = await mountDialog();

    // Queue a delete by mutating the reactive array in place.
    const state = wrapper.vm.$.setupState;
    state.pendingDeletes.splice(0, state.pendingDeletes.length, { annotationId: "annot-2" });
    await flushPromises();

    // Click Save Changes button (second button, after Cancel).
    const buttons = wrapper.findAll("button");
    expect(buttons.length).toBeGreaterThanOrEqual(2);
    await buttons[1].trigger("click");
    await flushPromises();

    // Should NOT emit error.
    expect(wrapper.emitted("error")).toBeFalsy();
    // Should emit saved.
    expect(wrapper.emitted("saved")).toBeTruthy();
  });
});
