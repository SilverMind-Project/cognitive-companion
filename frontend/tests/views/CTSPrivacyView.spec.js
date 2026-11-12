import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

const mocks = vi.hoisted(() => ({
  getCameras: vi.fn(),
  getPrivacyZones: vi.fn(),
  postPrivacyZones: vi.fn(),
  getSnapshot: vi.fn(),
  notify: vi.fn(),
}));

vi.mock("@/services/cts.js", () => ({
  cts: {
    getCameras: (...a) => mocks.getCameras(...a),
    getPrivacyZones: (...a) => mocks.getPrivacyZones(...a),
    postPrivacyZones: (...a) => mocks.postPrivacyZones(...a),
    getSnapshot: (...a) => mocks.getSnapshot(...a),
  },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: mocks.notify }),
}));

vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (url) => url }),
}));

vi.mock("@/components/cts/BlurToggle.vue", () => ({ default: { template: "<div />" } }));
vi.mock("@/components/cts/PolygonOnSnapshot.vue", () => ({
  default: { name: "PolygonOnSnapshot", props: ["imageUrl", "modelValue"], template: "<div />" },
}));

import CTSPrivacyView from "@/views/admin/CTSPrivacyView.vue";

const ZONE = {
  zone_id: "mirror",
  name: "Mirror",
  policy: "mask_region",
  enabled: true,
  polygon: [
    [0.1, 0.1],
    [0.4, 0.1],
    [0.4, 0.5],
  ],
};

const VUETIFY = [
  "v-alert",
  "v-btn",
  "v-card",
  "v-card-actions",
  "v-card-text",
  "v-card-title",
  "v-chip",
  "v-col",
  "v-dialog",
  "v-divider",
  "v-icon",
  "v-radio",
  "v-radio-group",
  "v-row",
  "v-select",
  "v-spacer",
  "v-switch",
  "v-text-field",
];

function mountView() {
  return mount(CTSPrivacyView, {
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

async function mountWithCamera() {
  const wrapper = mountView();
  await flushPromises();
  await wrapper.vm.selectCamera("kitchen-cam-1");
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getCameras.mockResolvedValue([{ id: "kitchen-cam-1", name: "Kitchen" }]);
  mocks.getPrivacyZones.mockResolvedValue({ zones: [structuredClone(ZONE)] });
  mocks.postPrivacyZones.mockResolvedValue(undefined);
  mocks.getSnapshot.mockResolvedValue("blob:snapshot");
});

describe("CTSPrivacyView", () => {
  it("offers exactly the orchestrator's privacy policies", () => {
    const wrapper = mountView();
    const values = wrapper.vm.POLICY_OPTIONS.map((option) => option.value);
    expect(values).toEqual(["mask_region", "blur_region", "drop_detection"]);
  });

  it("titles the zone dialog before any camera is chosen", async () => {
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.findComponent({ name: "AppDialog" }).props("title")).toBe("Privacy Zone");
  });

  it("starts a new zone with no polygon and only commits a named, closed shape", async () => {
    const wrapper = await mountWithCamera();
    wrapper.vm.openCreate();

    expect(wrapper.vm.form.polygon).toEqual([]);
    expect(wrapper.vm.canCommitZone).toBe(false);

    wrapper.vm.form.zone_id = "doorway";
    wrapper.vm.form.polygon = ZONE.polygon;
    expect(wrapper.vm.canCommitZone).toBe(true);
  });

  it("refuses a second zone with an existing ID", async () => {
    const wrapper = await mountWithCamera();
    wrapper.vm.openCreate();
    wrapper.vm.form.zone_id = "mirror";
    wrapper.vm.form.polygon = ZONE.polygon;

    expect(wrapper.vm.zoneIdError).toBeTruthy();
    wrapper.vm.commitZone();
    expect(wrapper.vm.zones).toHaveLength(1);
  });

  it("tracks unsaved changes, including removing the last zone", async () => {
    const wrapper = await mountWithCamera();
    expect(wrapper.vm.dirty).toBe(false);

    wrapper.vm.removeZone("mirror");
    expect(wrapper.vm.dirty).toBe(true);

    await wrapper.vm.saveZones();
    expect(mocks.postPrivacyZones).toHaveBeenCalledWith("kitchen-cam-1", []);
    expect(wrapper.vm.dirty).toBe(false);
  });

  it("asks before discarding unsaved zones when switching cameras", async () => {
    mocks.getCameras.mockResolvedValue([
      { id: "kitchen-cam-1", name: "Kitchen" },
      { id: "hall-cam", name: "Hall" },
    ]);
    const wrapper = await mountWithCamera();
    wrapper.vm.removeZone("mirror");

    const switching = wrapper.vm.selectCamera("hall-cam");
    await flushPromises();
    expect(wrapper.vm.confirmDialog).toBe(true);
    wrapper.vm.onCancel();
    await switching;

    expect(wrapper.vm.selectedCameraId).toBe("kitchen-cam-1");
    expect(wrapper.vm.zones).toHaveLength(0);
  });

  it("keeps the changes unsaved and says so when the tracker refuses them", async () => {
    const wrapper = await mountWithCamera();
    wrapper.vm.removeZone("mirror");
    mocks.postPrivacyZones.mockRejectedValueOnce(
      Object.assign(new Error("Tracker unavailable"), { status: 503 }),
    );

    await wrapper.vm.saveZones();

    expect(wrapper.vm.dirty).toBe(true);
    expect(mocks.notify).toHaveBeenCalledWith(
      expect.stringContaining("the tracker could not apply them"),
      "error",
    );

    // Other failures (a missing camera, a validation error) are not blamed on the tracker.
    mocks.postPrivacyZones.mockRejectedValueOnce(
      Object.assign(new Error("Camera not found"), { status: 404 }),
    );
    await wrapper.vm.saveZones();
    expect(mocks.notify).toHaveBeenLastCalledWith(
      "Privacy zones not saved. Camera not found",
      "error",
    );
  });
});
