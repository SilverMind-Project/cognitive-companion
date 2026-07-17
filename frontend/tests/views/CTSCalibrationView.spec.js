import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

const { mockNotify, mockAutoCalibrate, mockPostHomography, mockPostFloorRegion } = vi.hoisted(
  () => ({
    mockNotify: vi.fn(),
    mockAutoCalibrate: vi.fn(),
    mockPostHomography: vi.fn(),
    mockPostFloorRegion: vi.fn(),
  }),
);

vi.mock("@/services/cts.js", () => ({
  cts: {
    getCameras: vi.fn().mockResolvedValue([]),
    getSnapshot: vi.fn().mockResolvedValue("blob:snapshot"),
    getHomography: vi.fn().mockRejectedValue(new Error("missing")),
    previewHomography: vi.fn().mockResolvedValue({
      matrix: [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
      ],
      residuals_m: [0, 0, 0, 0],
      status: "ok",
    }),
    autoCalibrate: mockAutoCalibrate,
    postHomography: mockPostHomography,
    postFloorRegion: mockPostFloorRegion,
  },
}));

vi.mock("@/services/household.js", () => ({
  household: {
    getFloorPlan: vi.fn().mockResolvedValue({
      floor_plan_url: "/floor.png",
      floor_plan_width: 1000,
      floor_plan_height: 800,
      floor_meters_per_pixel: 0.01,
    }),
  },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({
    snack: ref(false),
    snackText: ref(""),
    snackColor: ref(""),
    notify: mockNotify,
  }),
}));

vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (url) => url }),
}));

vi.mock("@/composables/useCtsWebSocket.js", () => ({
  useCtsWebSocket: () => ({ status: ref("open"), disconnect: vi.fn() }),
}));

vi.mock("@/components/cts/BlurToggle.vue", () => ({
  default: { template: "<div />" },
}));

vi.mock("@/components/cts/CalibrationHealthPanel.vue", () => ({
  default: { template: "<div />" },
}));

const stubComponents = {
  "v-btn": { template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-select": { template: "<select><slot /></select>" },
  CcSegmentedToggle: { template: "<div />", props: ["modelValue", "options", "size"] },
  "v-chip": { template: "<span><slot /></span>" },
  "v-alert": { template: "<div><slot /></div>" },
  "v-table": { template: "<table><slot /></table>" },
  "v-text-field": { template: "<input />" },
  "v-progress-circular": { template: "<div />" },
  "v-expansion-panels": { template: "<div><slot /></div>" },
  "v-expansion-panel": { template: "<div><slot /></div>" },
  "v-expansion-panel-title": { template: "<div><slot /></div>" },
  "v-expansion-panel-text": { template: "<div><slot /></div>" },
  "v-snackbar": { template: "<div><slot /></div>" },
  "router-link": { template: "<a><slot /></a>" },
};

import CTSCalibrationView from "../../src/views/admin/CTSCalibrationView.vue";

async function mountView() {
  const wrapper = mount(CTSCalibrationView, {
    global: { stubs: stubComponents },
  });
  await flushPromises();
  return wrapper;
}

describe("CTSCalibrationView auto-calibration draft", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAutoCalibrate.mockResolvedValue({
      camera_id: "cam-1",
      draft_matrix: [
        [100, 0, -9999],
        [0, 100, -9999],
        [0, 0, 1],
      ],
      suggested_points: [
        { pixel: [120, 300], local_floor_m: [-3, 4] },
        { pixel: [360, 420], local_floor_m: [5, -2] },
      ],
      confidence: 0.8,
      inlier_count: 100,
      sample_count: 200,
      fov_deg: 70,
      image_width: 640,
      image_height: 480,
      method: "depth_auto_draft",
    });
    mockPostHomography.mockResolvedValue({
      camera_id: "cam-1",
      matrix: [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
      ],
      residuals_m: [0, 0, 0, 0],
      max_residual_m: 0,
      status: "ok",
    });
  });

  it("refine manually shows ghost camera suggestions without creating floor correspondences", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    state.autoResult = await mockAutoCalibrate();
    state.imgContentRect = {
      naturalWidth: 640,
      naturalHeight: 480,
      width: 640,
      height: 480,
      offsetX: 0,
      offsetY: 0,
    };

    state.populateFromAutoResult();

    expect(state.points).toEqual([]);
    expect(state.autoSuggestedPoints).toHaveLength(2);
    expect(state.autoSuggestedPoints[0].pixel).toEqual([120, 300]);
  });

  it("manual calibration still posts only anchored point correspondences", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    state.selectedCameraId = "cam-1";
    state.imgContentRect = {
      naturalWidth: 640,
      naturalHeight: 480,
      width: 640,
      height: 480,
      offsetX: 0,
      offsetY: 0,
    };
    state.points = [
      { pixel: [10, 300], floor_m: [1, 1] },
      { pixel: [200, 310], floor_m: [2, 1] },
      { pixel: [210, 450], floor_m: [2, 3] },
      { pixel: [20, 460], floor_m: [1, 3] },
    ];

    await state.runCalibration();

    expect(mockPostHomography).toHaveBeenCalledWith("cam-1", state.points, 640, 480);
  });
});

describe("CTSCalibrationView floor-region overlay", () => {
  const FLOOR_REGION = [
    [0.2, 0.4],
    [0.8, 0.4],
    [0.8, 0.9],
    [0.2, 0.9],
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockAutoCalibrate.mockResolvedValue({
      camera_id: "cam-1",
      draft_matrix: [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
      ],
      suggested_points: [],
      confidence: 0.8,
      inlier_count: 100,
      sample_count: 200,
      fov_deg: 70,
      image_width: 640,
      image_height: 480,
      method: "depth_auto_draft",
      floor_region_polygon: FLOOR_REGION,
    });
    mockPostFloorRegion.mockResolvedValue(undefined);
  });

  it("runAutoCalibrate populates floorRegionDraft when floor_region_polygon is returned", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    state.selectedCameraId = "cam-1";
    await state.runAutoCalibrate();
    await flushPromises();

    // setupState auto-unwraps refs: state.floorRegionDraft is the unwrapped value.
    expect(state.floorRegionDraft).toEqual(FLOOR_REGION);
  });

  it("saveFloorRegion calls cts.postFloorRegion with the current draft", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    state.selectedCameraId = "cam-1";
    state.floorRegionDraft = FLOOR_REGION;

    await state.saveFloorRegion("manual");
    await flushPromises();

    expect(mockPostFloorRegion).toHaveBeenCalledWith("cam-1", FLOOR_REGION, "manual");
    expect(mockNotify).toHaveBeenCalledWith(expect.stringContaining("manual"), "success");
  });

  it("discardFloorRegion clears floorRegionDraft", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    state.floorRegionDraft = FLOOR_REGION;
    state.discardFloorRegion();

    expect(state.floorRegionDraft).toBeNull();
  });

  it("onCameraChange clears floorRegionDraft", async () => {
    const wrapper = await mountView();
    const state = wrapper.vm.$.setupState;

    state.floorRegionDraft = FLOOR_REGION;
    state.selectedCameraId = "cam-1";
    // Simulate camera change (calls onCameraChange internally).
    await state.onCameraChange();
    await flushPromises();

    expect(state.floorRegionDraft).toBeNull();
  });
});
