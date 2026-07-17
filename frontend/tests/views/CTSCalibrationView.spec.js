import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

const { mockNotify, mockAutoCalibrate, mockPostHomography, mockPostFloorRegion, mockGetCameras } =
  vi.hoisted(() => ({
    mockNotify: vi.fn(),
    mockAutoCalibrate: vi.fn(),
    mockPostHomography: vi.fn(),
    mockPostFloorRegion: vi.fn(),
    mockGetCameras: vi.fn(),
  }));

vi.mock("@/services/cts.js", () => ({
  cts: {
    getCameras: (...a) => mockGetCameras(...a),
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

// CcSegmentedToggle is NOT mocked: it's a thin real component over v-btn (stubbed below),
// so mounting it for real gives us genuine click -> update:modelValue wiring for the
// pick/manual mode toggle without hand-rolling that logic in a stub.

const stubComponents = {
  "v-btn": {
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ["disabled", "loading", "icon", "size", "variant", "color", "prependIcon"],
  },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>", props: ["cols", "md"] },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-select": {
    template:
      '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\')"><option v-for="it in items" :key="it[itemValue]" :value="it[itemValue]">{{ it[itemTitle] }}</option></select>',
    props: ["modelValue", "items", "itemTitle", "itemValue", "label"],
  },
  "v-chip": { template: "<span><slot /></span>" },
  "v-alert": { template: "<div><slot /></div>" },
  "v-table": { template: "<table><slot /></table>" },
  "v-text-field": {
    template:
      '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ["modelValue", "label"],
  },
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

async function selectCamera(wrapper, cameraId) {
  await wrapper.find("select").setValue(cameraId);
  await flushPromises();
}

// Stubs the camera <img>'s natural size + bounding rect so onImageLoad computes a
// 1:1, no-letterbox content rect, then fires the real 'load' event handler.
async function loadCameraImage(wrapper, width = 640, height = 480) {
  const img = wrapper.find("img.snapshot-img").element;
  Object.defineProperty(img, "naturalWidth", { value: width, configurable: true });
  Object.defineProperty(img, "naturalHeight", { value: height, configurable: true });
  img.getBoundingClientRect = () => ({ left: 0, top: 0, width, height });
  await wrapper.find("img.snapshot-img").trigger("load");
  await flushPromises();
}

function clickCameraPane(wrapper, clientX, clientY) {
  return wrapper.find(".snapshot-container").trigger("click", { clientX, clientY });
}

describe("CTSCalibrationView auto-calibration draft", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCameras.mockResolvedValue([
      { id: "cam-1", name: "Cam 1" },
      { id: "cam-2", name: "Cam 2" },
    ]);
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
    await selectCamera(wrapper, "cam-1");
    await loadCameraImage(wrapper);

    const autoBtn = wrapper.findAll("button").find((b) => b.text() === "Auto-calibrate");
    await autoBtn.trigger("click");
    await flushPromises();

    const refineBtn = wrapper.findAll("button").find((b) => b.text() === "Refine manually");
    await refineBtn.trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("No points yet");
    const markers = wrapper.findAll(".auto-suggestion-marker");
    expect(markers).toHaveLength(2);
    expect(markers[0].find("circle[stroke='#38bdf8']").attributes("cx")).toBe("120");
    expect(markers[0].find("circle[stroke='#38bdf8']").attributes("cy")).toBe("300");
  });

  it("manual calibration still posts only anchored point correspondences", async () => {
    const wrapper = await mountView();
    await selectCamera(wrapper, "cam-1");

    // Switch to Manual Entry mode so camera clicks add a point directly
    // (no floor-plan anchor click required).
    const manualBtn = wrapper.findAll("button").find((b) => b.text() === "Manual Entry");
    await manualBtn.trigger("click");
    await flushPromises();

    await loadCameraImage(wrapper);

    const pixels = [
      [10, 300],
      [200, 310],
      [210, 450],
      [20, 460],
    ];
    const floorMs = [
      [1, 1],
      [2, 1],
      [2, 3],
      [1, 3],
    ];
    for (const [x, y] of pixels) {
      await clickCameraPane(wrapper, x, y);
    }
    await flushPromises();

    // Fill in floor_m X/Y for each point row via the manual-entry inputs.
    const inputs = wrapper.findAll(".point-row input");
    expect(inputs).toHaveLength(8); // 4 rows x (X, Y)
    for (let i = 0; i < 4; i++) {
      await inputs[i * 2].setValue(String(floorMs[i][0]));
      await inputs[i * 2 + 1].setValue(String(floorMs[i][1]));
    }

    const calibrateBtn = wrapper.findAll("button").find((b) => b.text() === "Calibrate");
    expect(calibrateBtn.attributes("disabled")).toBeFalsy();
    await calibrateBtn.trigger("click");
    await flushPromises();

    expect(mockPostHomography).toHaveBeenCalledWith(
      "cam-1",
      [
        { pixel: [10, 300], floor_m: [1, 1] },
        { pixel: [200, 310], floor_m: [2, 1] },
        { pixel: [210, 450], floor_m: [2, 3] },
        { pixel: [20, 460], floor_m: [1, 3] },
      ],
      640,
      480,
    );
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
    mockGetCameras.mockResolvedValue([
      { id: "cam-1", name: "Cam 1" },
      { id: "cam-2", name: "Cam 2" },
    ]);
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

  async function getToFloorRegionDraft(wrapper) {
    await selectCamera(wrapper, "cam-1");
    await loadCameraImage(wrapper);
    const autoBtn = wrapper.findAll("button").find((b) => b.text() === "Auto-calibrate");
    await autoBtn.trigger("click");
    await flushPromises();
  }

  it("runAutoCalibrate populates the Floor Region card when floor_region_polygon is returned", async () => {
    const wrapper = await mountView();
    await getToFloorRegionDraft(wrapper);

    expect(wrapper.text()).toContain("Floor Region");
    expect(wrapper.text()).toContain("4 vertices");
    const polygon = wrapper.find("polygon");
    expect(polygon.exists()).toBe(true);
    // FLOOR_REGION[0] = [0.2, 0.4] normalised -> SVG coords in the 640x480 natural viewBox.
    expect(polygon.attributes("points")).toContain("128.0,192.0");
  });

  it("saveFloorRegion calls cts.postFloorRegion with the current draft", async () => {
    const wrapper = await mountView();
    await getToFloorRegionDraft(wrapper);

    const saveBtn = wrapper.findAll("button").find((b) => b.text() === "Save Region");
    await saveBtn.trigger("click");
    await flushPromises();

    expect(mockPostFloorRegion).toHaveBeenCalledWith("cam-1", FLOOR_REGION, "manual");
    expect(mockNotify).toHaveBeenCalledWith(expect.stringContaining("manual"), "success");
  });

  it("discardFloorRegion clears the draft and hides the Floor Region card", async () => {
    const wrapper = await mountView();
    await getToFloorRegionDraft(wrapper);
    expect(wrapper.text()).toContain("Floor Region");

    const discardBtn = wrapper.findAll("button").find((b) => b.text() === "Discard");
    await discardBtn.trigger("click");
    await flushPromises();

    expect(wrapper.text()).not.toContain("Floor Region");
  });

  it("changing camera clears the floor-region draft", async () => {
    const wrapper = await mountView();
    await getToFloorRegionDraft(wrapper);
    expect(wrapper.text()).toContain("Floor Region");

    await selectCamera(wrapper, "cam-2");

    expect(wrapper.text()).not.toContain("Floor Region");
  });
});
