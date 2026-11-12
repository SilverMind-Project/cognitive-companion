import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

const { mockGetCameras, mockUpdateCamera, mockCreateCamera, mockNotify } = vi.hoisted(() => ({
  mockGetCameras: vi.fn(),
  mockUpdateCamera: vi.fn(),
  mockCreateCamera: vi.fn(),
  mockNotify: vi.fn(),
}));

vi.mock("@/services/cts.js", () => ({
  cts: {
    getCameras: (...a) => mockGetCameras(...a),
    getVisibilityPolygons: vi.fn().mockResolvedValue({ cameras: [] }),
    updateCamera: (...a) => mockUpdateCamera(...a),
    createCamera: (...a) => mockCreateCamera(...a),
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
