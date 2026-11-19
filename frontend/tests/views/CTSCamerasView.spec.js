import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

const {
  mockGetCameras,
  mockUpdateCamera,
  mockCreateCamera,
  mockGetCameraOptics,
  mockPreviewCameraOptics,
  mockNotify,
} = vi.hoisted(() => ({
  mockGetCameras: vi.fn(),
  mockUpdateCamera: vi.fn(),
  mockCreateCamera: vi.fn(),
  mockGetCameraOptics: vi.fn(),
  mockPreviewCameraOptics: vi.fn(),
  mockNotify: vi.fn(),
}));

vi.mock("@/services/cts.js", () => ({
  cts: {
    getCameras: (...a) => mockGetCameras(...a),
    getVisibilityPolygons: vi.fn().mockResolvedValue({ cameras: [] }),
    updateCamera: (...a) => mockUpdateCamera(...a),
    createCamera: (...a) => mockCreateCamera(...a),
    getCameraOptics: (...a) => mockGetCameraOptics(...a),
    previewCameraOptics: (...a) => mockPreviewCameraOptics(...a),
  },
}));

vi.mock("@/services/api.js", () => ({
  api: { getRooms: vi.fn().mockResolvedValue([{ id: 3, name: "Kitchen" }]) },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: mockNotify }),
}));

vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (url) => url }),
}));

vi.mock("@/composables/useFloorPlanCanvas.js", () => ({
  useFloorPlanCanvas: () => ({ floorPlanUrl: ref(null), loadFloorPlan: vi.fn() }),
}));

vi.mock("@/components/cts/BlurToggle.vue", () => ({ default: { template: "<div />" } }));
vi.mock("@/components/cts/cameras/CTSCameraPlacementMap.vue", () => ({
  default: { template: "<div />" },
}));

import CTSCamerasView from "@/views/admin/CTSCamerasView.vue";

const CAMERA = {
  id: "kitchen-cam-1",
  name: "Kitchen",
  rtsp_url: "rtsp://x",
  room_name: "Kitchen",
  room_id: 3,
  enabled: true,
  face_id_enabled: true,
  face_id_min_raw_similarity: 0.55,
  role: "face_capable",
  horizontal_fov_deg: 90,
  mounting_height_m: null,
  tilt_deg: null,
  ir_capable: true,
  has_homography: true,
  frame_natural_width: 2560,
  frame_natural_height: 1440,
};

const OPTICS_RESPONSE = {
  camera_id: "kitchen-cam-1",
  horizontal_fov_deg: 90.0,
  frame_natural_width: 2560,
  frame_natural_height: 1440,
  observed_stream_width: 2560,
  observed_stream_height: 1440,
  stream_size_mismatch: false,
  focal_length_px: 1280.0,
  distance_for_24px_m: 3.36,
  distances: [
    { distance_m: 1.0, interocular_px: 80.64, band: "excellent" },
    { distance_m: 2.0, interocular_px: 40.32, band: "excellent" },
    { distance_m: 3.0, interocular_px: 26.88, band: "good" },
    { distance_m: 4.0, interocular_px: 20.16, band: "marginal" },
    { distance_m: 5.0, interocular_px: 16.13, band: "marginal" },
  ],
  bands: [
    { band: "poor", min_px: null, max_px: 16.0 },
    { band: "marginal", min_px: 16.0, max_px: 24.0 },
    { band: "good", min_px: 24.0, max_px: 40.0 },
    { band: "excellent", min_px: 40.0, max_px: null },
  ],
  missing_inputs: [],
};

const VUETIFY = [
  "v-alert",
  "v-autocomplete",
  "v-btn",
  "v-card",
  "v-card-actions",
  "v-card-text",
  "v-card-title",
  "v-chip",
  "v-col",
  "v-data-table",
  "v-dialog",
  "v-divider",
  "v-icon",
  "v-img",
  "v-progress-circular",
  "v-radio",
  "v-radio-group",
  "v-row",
  "v-sheet",
  "v-spacer",
  "v-switch",
  "v-tab",
  "v-table",
  "v-tabs",
  "v-text-field",
  "v-window",
  "v-window-item",
];

function mountView() {
  return mount(CTSCamerasView, {
    global: {
      stubs: {
        ...Object.fromEntries(VUETIFY.map((name) => [name, true])),
        "v-data-table": {
          props: ["headers", "items", "loading"],
          template:
            '<div><div v-for="item in items" :key="item.id" :data-camera-id="item.id"><slot name="item.enabled" :item="item" /><slot name="item.has_homography" :item="item" /></div></div>',
        },
        DialogHeader: true,
        DialogFooter: true,
      },
      renderStubDefaultSlot: true,
      mocks: { $vuetify: { display: { smAndDown: false } } },
    },
  });
}

describe("CTSCamerasView face similarity floor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCameras.mockResolvedValue([CAMERA]);
    mockUpdateCamera.mockResolvedValue({});
    mockGetCameraOptics.mockResolvedValue(OPTICS_RESPONSE);
    mockPreviewCameraOptics.mockResolvedValue(OPTICS_RESPONSE);
  });

  it("labels the floor as an advanced raw-similarity setting and loads it", async () => {
    const wrapper = mountView();
    await flushPromises();

    wrapper.vm.openEdit(CAMERA);
    await flushPromises();

    const field = wrapper
      .findAll("v-text-field-stub")
      .find((f) => f.attributes("label")?.startsWith("Minimum raw face similarity"));
    expect(field?.attributes("label")).toBe("Minimum raw face similarity (advanced, leave empty)");
    expect(wrapper.vm.form.face_id_min_raw_similarity).toBe(0.55);
    expect(wrapper.html()).not.toContain("Min confidence");
  });

  it("sends null, not an empty string, for cleared optional numbers", async () => {
    const wrapper = mountView();
    await flushPromises();
    wrapper.vm.openEdit(CAMERA);

    // A cleared v-model.number input holds "".
    wrapper.vm.form.face_id_min_raw_similarity = "";
    wrapper.vm.form.horizontal_fov_deg = "";
    await wrapper.vm.saveCamera();

    expect(mockUpdateCamera).toHaveBeenCalledTimes(1);
    const [cameraId, patch] = mockUpdateCamera.mock.calls[0];
    expect(cameraId).toBe("kitchen-cam-1");
    expect(patch.face_id_min_raw_similarity).toBeNull();
    expect(patch.horizontal_fov_deg).toBeNull();
    expect(patch).not.toHaveProperty("face_id_min_confidence");
  });

  it("keeps a set floor as a number", async () => {
    const wrapper = mountView();
    await flushPromises();
    wrapper.vm.openEdit(CAMERA);

    await wrapper.vm.saveCamera();

    const [, patch] = mockUpdateCamera.mock.calls[0];
    expect(patch.face_id_min_raw_similarity).toBe(0.55);
  });
});

describe("CTSCamerasView sectioned camera dialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCameras.mockResolvedValue([CAMERA]);
    mockCreateCamera.mockResolvedValue({});
  });

  it("groups the form into General, Identity, Geometry, and Placement sections", async () => {
    const wrapper = mountView();
    await flushPromises();
    wrapper.vm.openCreate();
    await flushPromises();

    const keys = wrapper.vm.cameraSections.map((section) => section.key);
    expect(keys).toEqual(["general", "identity", "geometry", "placement"]);
    expect(wrapper.vm.activeSection).toBe("general");
  });

  it("returns to General and flags it instead of sending an incomplete create", async () => {
    const wrapper = mountView();
    await flushPromises();
    wrapper.vm.openCreate();
    wrapper.vm.activeSection = "geometry";

    await wrapper.vm.saveCamera();

    expect(mockCreateCamera).not.toHaveBeenCalled();
    expect(wrapper.vm.activeSection).toBe("general");
    expect(wrapper.vm.fieldErrors.id).toBeTruthy();
    expect(wrapper.vm.fieldErrors.location).toBeTruthy();
    expect(wrapper.vm.cameraSections[0].error).toBe(true);
  });

  it("clears the field errors once the operator fills them in", async () => {
    const wrapper = mountView();
    await flushPromises();
    wrapper.vm.openCreate();
    await wrapper.vm.saveCamera();

    wrapper.vm.form.id = "hall-cam";
    wrapper.vm.form.room_id = 3;
    await flushPromises();

    expect(wrapper.vm.fieldErrors).toEqual({});
    await wrapper.vm.saveCamera();
    expect(mockCreateCamera).toHaveBeenCalledWith(
      expect.objectContaining({ id: "hall-cam", room_id: 3, room_name: "" }),
    );
  });
});

describe("CTSCamerasView ingest health badge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a No frames badge when an enabled camera's last frame is older than 60 s", async () => {
    mockGetCameras.mockResolvedValue([
      {
        ...CAMERA,
        enabled: true,
        health: { status: "degraded", last_frame_age_s: 75.2, fetch_backoff_s: 16.0 },
      },
    ]);
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("Active");
    expect(wrapper.text()).toContain("No frames");
  });

  it("does not show No frames when last frame age is 60 s or less or camera is disabled", async () => {
    mockGetCameras.mockResolvedValue([
      {
        ...CAMERA,
        id: "fresh-cam",
        enabled: true,
        health: { status: "healthy", last_frame_age_s: 12.0, fetch_backoff_s: 0.0 },
      },
      {
        ...CAMERA,
        id: "disabled-cam",
        enabled: false,
        health: { status: "stopped", last_frame_age_s: 120.0, fetch_backoff_s: 0.0 },
      },
    ]);
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).not.toContain("No frames");
  });
});

describe("CTSCamerasView placement calculator and camera profile", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCameras.mockResolvedValue([CAMERA]);
    mockUpdateCamera.mockResolvedValue({});
    mockGetCameraOptics.mockResolvedValue(OPTICS_RESPONSE);
    mockPreviewCameraOptics.mockResolvedValue({
      ...OPTICS_RESPONSE,
      camera_id: null,
      horizontal_fov_deg: 60.0,
      focal_length_px: 2217.03,
      distance_for_24px_m: 5.82,
      distances: [{ distance_m: 2.0, interocular_px: 69.84, band: "excellent" }],
    });
  });

  it("renders values returned by the optics endpoint without client-side formulas", async () => {
    const wrapper = mountView();
    await flushPromises();

    wrapper.vm.openEdit(CAMERA);
    await flushPromises();

    expect(mockGetCameraOptics).toHaveBeenCalledWith("kitchen-cam-1");
    expect(wrapper.text()).toContain("Observed stream: 2560 × 1440 px");
    expect(wrapper.text()).toContain("1280 px");
    expect(wrapper.text()).toContain("up to 3.36 m");
    expect(wrapper.text()).toContain("40.3 px");
    expect(wrapper.text()).toContain("Excellent");
  });

  it("calls the stateless preview endpoint when horizontal FOV changes", async () => {
    const wrapper = mountView();
    await flushPromises();

    wrapper.vm.openEdit(CAMERA);
    await flushPromises();

    wrapper.vm.form.horizontal_fov_deg = 60;
    await flushPromises();

    expect(mockPreviewCameraOptics).toHaveBeenCalledWith({
      horizontal_fov_deg: 60,
      frame_natural_width: 2560,
      frame_natural_height: 1440,
    });
    expect(wrapper.text()).toContain("2217 px");
    expect(wrapper.text()).toContain("up to 5.82 m");
    expect(wrapper.text()).toContain("69.8 px");
  });

  it("round-trips ir_capable and flags uncalibrated face_capable cameras", async () => {
    const uncalibratedIdCam = {
      ...CAMERA,
      id: "hall-id-1",
      role: "face_capable",
      has_homography: false,
      ir_capable: true,
    };
    mockGetCameras.mockResolvedValue([uncalibratedIdCam]);

    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("Needs calibration");

    wrapper.vm.openEdit(uncalibratedIdCam);
    await flushPromises();
    expect(wrapper.text()).toContain("This identification-point camera has no floor calibration");
    expect(wrapper.vm.form.ir_capable).toBe(true);

    wrapper.vm.form.ir_capable = false;
    await wrapper.vm.saveCamera();
    expect(mockUpdateCamera).toHaveBeenCalledWith(
      "hall-id-1",
      expect.objectContaining({ ir_capable: false }),
    );
  });
});
