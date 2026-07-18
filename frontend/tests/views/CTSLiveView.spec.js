import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

const mocks = vi.hoisted(() => ({
  getCameras: vi.fn(),
  getSnapshot: vi.fn(),
  applyCorrection: vi.fn(),
  notifyInfo: vi.fn(),
  wsStatus: { __v_isRef: true, value: "open" },
}));

let capturedOnMessage = null;

vi.mock("@/services/cts", () => ({
  cts: {
    getCameras: (...a) => mocks.getCameras(...a),
    getSnapshot: (...a) => mocks.getSnapshot(...a),
    applyCorrection: (...a) => mocks.applyCorrection(...a),
  },
}));

vi.mock("@/composables/useCtsWebSocket.js", () => ({
  useCtsWebSocket: (onMessage) => {
    capturedOnMessage = onMessage;
    return { status: mocks.wsStatus, disconnect: vi.fn() };
  },
}));

vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({
    state: { enabled: false, reducedMotion: false },
    actions: { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() },
  }),
}));

vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (url) => url }),
}));

vi.mock("@/composables/useIdentityColor.js", () => ({
  identityColor: (id) => `color-${id}`,
}));

vi.mock("@/composables/useAnnotationStyle.js", () => ({
  HALO: { color: "black" },
  postureColor: () => "red",
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { info: mocks.notifyInfo, error: vi.fn(), success: vi.fn() } }),
}));

vi.mock("@/components/marauders/MaraudersInkBox.vue", () => ({
  default: { template: "<g />", props: ["x", "y", "w", "h", "seedKey", "color"] },
}));

vi.mock("@/components/cts/BlurToggle.vue", () => ({
  default: { template: "<div data-testid='blur-toggle' />" },
}));

import CTSLiveView from "../../src/views/admin/CTSLiveView.vue";

const stubs = {
  "v-card": { template: "<section><slot /></section>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-alert": {
    template: '<div v-if="modelValue !== false"><slot /></div>',
    props: ["type", "modelValue"],
  },
  "v-divider": { template: "<hr />" },
  "v-spacer": { template: "<div />" },
  "v-icon": { template: "<i><slot /></i>", props: ["size", "color"] },
  "v-chip": {
    template: "<span><slot name='prepend' /><slot /></span>",
    props: ["color", "size", "variant", "prependIcon", "density"],
  },
  "v-select": {
    template:
      '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><option v-for="it in items" :key="it.value ?? it.id" :value="it.value ?? it.id">{{ it.label ?? it.name }}</option></select>',
    props: ["modelValue", "items", "itemTitle", "itemValue", "label", "clearable"],
  },
  "v-switch": {
    template:
      '<input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" />',
    props: ["modelValue", "label", "color"],
  },
  "v-dialog": {
    template: '<div v-if="modelValue"><slot /></div>',
    props: ["modelValue", "maxWidth", "persistent"],
  },
  "v-text-field": {
    template:
      '<input :value="modelValue" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ["modelValue", "label", "placeholder"],
  },
  "v-avatar": { template: "<div><slot /></div>", props: ["size"] },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-btn": {
    template: "<button @click=\"$emit('click')\"><slot /></button>",
    props: ["icon", "variant", "color", "loading", "disabled"],
  },
};

function mountView(props = {}) {
  return mount(CTSLiveView, { props, global: { stubs } });
}

const CAM1_FRAME = {
  type: "cts_live_frame",
  camera_id: "cam1",
  frame_url: "/cam1.jpg",
  frame_width: 1920,
  frame_height: 1080,
  room_name: "Kitchen",
  detections: [
    {
      detection_id: "d1",
      ph_id: "ph1",
      identity_id: "alice",
      identity_confidence: 0.9,
      bbox: { x_min: 100, y_min: 100, x_max: 300, y_max: 400 },
      posture: "standing",
    },
  ],
};

beforeEach(() => {
  capturedOnMessage = null;
  vi.clearAllMocks();
  mocks.wsStatus.value = "open";
  mocks.getCameras.mockResolvedValue([
    { id: "cam1", name: "Kitchen Cam" },
    { id: "cam2", name: "Hallway Cam" },
  ]);
  mocks.getSnapshot.mockResolvedValue("blob:snapshot-url");
  mocks.applyCorrection.mockResolvedValue({});
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("CTSLiveView", () => {
  it("renders the header and websocket status chip", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("Live Tracking");
    expect(wrapper.text()).toContain("open");
  });

  it("loads known cameras and renders a picker per slot", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(mocks.getCameras).toHaveBeenCalled();
    const pickers = wrapper.findAll(".live-tile select");
    expect(pickers.length).toBeGreaterThan(0);
  });

  it("renders a bbox rect for an incoming WS detection, hidden when Bboxes is off", async () => {
    const wrapper = mountView();
    await flushPromises();
    capturedOnMessage(CAM1_FRAME);
    await flushPromises();

    expect(wrapper.find("img.live-tile-img").attributes("src")).toBe("/cam1.jpg");
    let rect = wrapper.find("rect");
    expect(rect.exists()).toBe(true);
    expect(rect.attributes("x")).toBe("100");
    expect(rect.attributes("y")).toBe("100");
    expect(rect.attributes("width")).toBe("200");
    expect(rect.attributes("height")).toBe("300");

    // Toggle "Bboxes" off (first switch)
    const bboxSwitch = wrapper.findAll('input[type="checkbox"]')[0];
    await bboxSwitch.setValue(false);
    rect = wrapper.find("rect");
    expect(rect.exists()).toBe(false);
  });

  it("renders the identity label text when Labels is on", async () => {
    const wrapper = mountView();
    await flushPromises();
    capturedOnMessage(CAM1_FRAME);
    await flushPromises();
    expect(wrapper.text()).toContain("alice");
  });

  it("clicking a detection bbox opens the correction dialog pre-filled, and submitting applies it", async () => {
    const wrapper = mountView();
    await flushPromises();
    capturedOnMessage(CAM1_FRAME);
    await flushPromises();

    await wrapper.find("rect").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("ph1");
    expect(wrapper.text()).toContain("cam1");
    expect(wrapper.text()).toContain("alice");

    const inputs = wrapper.findAll("input");
    const newIdInput = inputs.find((i) => i.attributes("placeholder")?.includes("UNKNOWN"));
    await newIdInput.setValue("bob");

    const applyBtn = wrapper.findAll("button").find((b) => b.text().includes("Apply override"));
    await applyBtn.trigger("click");
    await flushPromises();

    expect(mocks.applyCorrection).toHaveBeenCalledWith({
      ph_id: "ph1",
      new_identity_id: "bob",
      reason: "manual",
    });
  });

  it("shows the cross-camera banner once the same identity appears on 2+ cameras", async () => {
    const wrapper = mountView();
    await flushPromises();
    capturedOnMessage(CAM1_FRAME);
    capturedOnMessage({
      type: "cts_live_frame",
      camera_id: "cam2",
      frame_url: "/cam2.jpg",
      detections: [
        {
          detection_id: "d2",
          ph_id: "ph2",
          identity_id: "alice",
          bbox: { x_min: 0, y_min: 0, x_max: 100, y_max: 100 },
        },
      ],
    });
    await flushPromises();
    expect(wrapper.text()).toContain("Cross-camera activity");
    expect(wrapper.text()).toContain("2 cams");
  });

  it("persists the per-slot camera selection to localStorage", async () => {
    const wrapper = mountView();
    await flushPromises();
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const picker = wrapper.findAll(".live-tile select")[0];
    await picker.setValue("cam2");
    await flushPromises();
    expect(setItemSpy).toHaveBeenCalledWith(
      "cts_live_selected_cameras",
      expect.stringContaining("cam2"),
    );
  });

  it("on image load error, clears frame_url and falls back to the polled snapshot", async () => {
    const wrapper = mountView();
    await flushPromises();
    capturedOnMessage(CAM1_FRAME);
    await flushPromises();
    const img = wrapper.find("img.live-tile-img");
    expect(img.attributes("src")).toBe("/cam1.jpg");
    await img.trigger("error");
    await flushPromises();
    // Same frame_url would immediately v-if back in if not cleared; instead it falls
    // through to the v-else-if snapshot branch (same CSS class, different source).
    expect(wrapper.find("img.live-tile-img").attributes("src")).toBe("blob:snapshot-url");
  });

  it("marks a camera stale once its last frame is older than the threshold", async () => {
    vi.useFakeTimers();
    const wrapper = mountView();
    await flushPromises();
    capturedOnMessage(CAM1_FRAME);
    await flushPromises();
    expect(wrapper.text()).not.toContain("Last seen");

    await vi.advanceTimersByTimeAsync(20_000);
    await flushPromises();
    expect(wrapper.text()).toContain("Last seen");
  });
});
