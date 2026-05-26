import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

// ── Mocks ──────────────────────────────────────────────────────────────────

// Capture the onMessage callback so we can simulate WebSocket frames.
let _onWsMessage = null;

vi.mock("@/composables/useCtsWebSocket", () => ({
  useCtsWebSocket: (onMessage) => {
    _onWsMessage = onMessage;
    return { status: ref("open"), disconnect: vi.fn() };
  },
}));

vi.mock("@/composables/useNotify", () => ({
  useNotify: () => ({
    snack: ref(false),
    snackText: ref(""),
    snackColor: ref(""),
    notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  }),
}));

vi.mock("@/services/household", () => ({
  household: {
    getFloorPlan: vi.fn().mockResolvedValue({}),
    getRooms: vi.fn().mockResolvedValue([]),
    postFloorPlan: vi.fn().mockResolvedValue({}),
    putRoom: vi.fn(),
  },
}));

vi.mock("@/services/cts", () => ({
  cts: {
    getVisibilityPolygons: vi.fn().mockResolvedValue({ cameras: [] }),
  },
}));

// Stub Vuetify components.
const stubComponents = {
  "v-btn": { template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div class='v-card'><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": { template: "<li><slot /></li>" },
  "v-list-item-title": { template: "<span><slot /></span>" },
  "v-list-item-subtitle": { template: "<span><slot /></span>" },
  "v-chip": { template: "<span class='v-chip'><slot /></span>" },
  "v-chip-group": { template: "<div><slot /></div>" },
  "v-alert": { template: "<div><slot /></div>" },
  "v-divider": { template: "<hr />" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
  "v-snackbar": { template: "<div><slot /></div>" },
  "v-overlay": { template: "<div><slot /></div>" },
  "v-tabs": { template: "<div><slot /></div>" },
  "v-tab": { template: "<div><slot /></div>" },
  "v-window": { template: "<div><slot /></div>" },
  "v-window-item": { template: "<div><slot /></div>" },
  "v-btn-toggle": { template: "<div><slot /></div>" },
  "v-file-input": { template: "<input type='file' />" },
  "v-text-field": { template: "<input />" },
  "v-select": { template: "<select><slot /></select>" },
  "v-autocomplete": { template: "<input />" },
  "v-data-table": { template: "<table><slot /></table>" },
  "v-img": { template: "<img />" },
  "v-img-placeholder": { template: "<div />" },
  "v-progress-circular": { template: "<div />" },
  "v-checkbox-btn": { template: "<input type='checkbox' />" },
  "v-navigation-drawer": { template: "<div><slot /></div>" },
  "v-slider": { template: "<input type='range' />" },
  PolygonOnSnapshot: { template: "<div />" },
  "router-link": { template: "<a><slot /></a>" },
};

import CTSFloorPlanView from "../../src/views/admin/CTSFloorPlanView.vue";

function makeFrame(overrides = {}) {
  return {
    type: "cts_live_frame",
    camera_id: "cam-1",
    frame_width: 640,
    frame_height: 480,
    detections: [],
    ...overrides,
  };
}

function makeDetection(overrides = {}) {
  return {
    global_track_id: "gt-001",
    identity_id: null,
    display_name: null,
    floor_calibrated: true,
    floor_x: 5.0,
    floor_y: 3.0,
    identity_confidence: 0,
    bbox: { x_min: 100, y_min: 200, x_max: 300, y_max: 400 },
    ...overrides,
  };
}

/** Set up floor plan dimensions so projection works. */
function setFloorPlan(wrapper, width = 1448, height = 1086, mpp = 0.0086) {
  const vm = wrapper.vm.$.setupState;
  vm.fpWidth = width;
  vm.fpHeight = height;
  vm.fpMpp = mpp;
}

function getTrails(wrapper) {
  return wrapper.vm.$.setupState.identityTrails;
}

async function mountView() {
  const wrapper = mount(CTSFloorPlanView, {
    global: { stubs: stubComponents },
  });
  await flushPromises();
  return wrapper;
}

describe("CTSFloorPlanView — live frame handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    _onWsMessage = null;
  });

  describe("trail rendering", () => {
    it("drops uncalibrated detections from floor-plan trails", async () => {
      const wrapper = await mountView();
      setFloorPlan(wrapper);

      const cal = makeDetection({ global_track_id: "gt-1", floor_calibrated: true, floor_x: 5, floor_y: 3 });
      const uncal = makeDetection({ global_track_id: "gt-2", floor_calibrated: false, floor_x: 5, floor_y: 3 });
      const frame = makeFrame({ detections: [cal, uncal] });

      _onWsMessage(frame);
      await flushPromises();

      const trails = getTrails(wrapper);
      const keys = Object.keys(trails);
      expect(keys).toContain("gt:gt-1");
      expect(keys).not.toContain("gt:gt-2");
    });

    it("creates a single contiguous trail keyed by identity_id when same GT is later identified", async () => {
      const wrapper = await mountView();
      setFloorPlan(wrapper);

      // Frame 1: detection with GT, no identity.
      const frame1 = makeFrame({
        detections: [makeDetection({ global_track_id: "gt-same", identity_id: null, floor_x: 5, floor_y: 3 })],
      });
      _onWsMessage(frame1);
      await flushPromises();

      // Frame 2: same GT, now with identity assigned by orchestrator healing pass.
      const frame2 = makeFrame({
        detections: [makeDetection({ global_track_id: "gt-same", identity_id: "alice", display_name: "Alice", floor_x: 6, floor_y: 4 })],
      });
      _onWsMessage(frame2);
      await flushPromises();

      const trails = getTrails(wrapper);
      expect(trails["id:alice"]).toBeDefined();
      // The old gt: trail should have been merged and deleted.
      expect(trails["gt:gt-same"]).toBeUndefined();
      // The merged trail should contain points from both frames.
      expect(trails["id:alice"].points.length).toBe(2);
    });

    it("uses stable identity color across frames where only GT changes", async () => {
      const wrapper = await mountView();
      setFloorPlan(wrapper);

      const frame1 = makeFrame({
        detections: [makeDetection({ global_track_id: "gt-aaa", identity_id: "bob", display_name: "Bob", floor_x: 5, floor_y: 3 })],
      });
      _onWsMessage(frame1);
      await flushPromises();

      const trails1 = getTrails(wrapper);
      const color1 = trails1["id:bob"].color;

      // Frame 2: same identity, different GT.
      const frame2 = makeFrame({
        detections: [makeDetection({ global_track_id: "gt-bbb", identity_id: "bob", display_name: "Bob", floor_x: 6, floor_y: 4 })],
      });
      _onWsMessage(frame2);
      await flushPromises();

      const trails2 = getTrails(wrapper);
      const color2 = trails2["id:bob"].color;
      expect(color1).toBe(color2);
    });
  });

  describe("uncalibratedDetCount", () => {
    it("increments when uncalibrated detections arrive with a valid floor plan", async () => {
      const wrapper = await mountView();
      setFloorPlan(wrapper);

      const uncal = makeDetection({ global_track_id: "gt-3", floor_calibrated: false, floor_x: 5, floor_y: 3 });
      const frame = makeFrame({ detections: [uncal] });

      _onWsMessage(frame);
      await flushPromises();

      expect(wrapper.vm.$.setupState.uncalibratedDetCount).toBeGreaterThan(0);
    });

    it("does not count uncalibrated detections when floor plan is missing", async () => {
      const wrapper = await mountView();

      const uncal = makeDetection({ global_track_id: "gt-4", floor_calibrated: false, floor_x: 5, floor_y: 3 });
      const frame = makeFrame({ detections: [uncal] });

      _onWsMessage(frame);
      await flushPromises();

      expect(wrapper.vm.$.setupState.uncalibratedDetCount).toBe(0);
    });
  });
});
