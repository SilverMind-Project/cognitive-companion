import { describe, expect, it, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { nextTick, ref } from "vue";
import DoorZoneEditor from "@/components/cts/DoorZoneEditor.vue";

const createTransitZone = vi.fn();
const updateTransitZone = vi.fn();
const deleteTransitZone = vi.fn();
const notifySuccess = vi.fn();
const notifyError = vi.fn();
const showConfirm = vi.fn();

vi.mock("@/services/cts.js", () => ({
  cts: {
    createTransitZone: (...args) => createTransitZone(...args),
    updateTransitZone: (...args) => updateTransitZone(...args),
    deleteTransitZone: (...args) => deleteTransitZone(...args),
  },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: Object.assign(vi.fn(), { success: notifySuccess, error: notifyError }) }),
}));

vi.mock("@/composables/useMaraudersMode.js", () => ({
  useMaraudersMode: () => ({
    state: { enabled: false, reducedMotion: false },
    actions: { enable: vi.fn(), disable: vi.fn(), toggle: vi.fn() },
  }),
}));

vi.mock("@/composables/useConfirm.js", () => ({
  useConfirm: () => ({
    confirmDialog: ref(false),
    confirmTitle: ref(""),
    confirmText: ref(""),
    confirmLabel: ref("Confirm"),
    cancelLabel: ref("Cancel"),
    confirmColor: ref("error"),
    showConfirm,
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  }),
}));

const rooms = [
  { id: 1, name: "Bathroom", floor_polygon: [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]] },
  { id: 2, name: "Hallway", floor_polygon: [[0.5, 0.1], [0.9, 0.1], [0.9, 0.4], [0.5, 0.4]] },
];

const stubs = {
  CcZoomControls: { template: "<div />" },
  "v-alert": { template: "<div><slot /></div>" },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<section><slot /></section>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-text-field": { template: "<input />" },
  "v-select": { template: "<select />" },
  "v-btn": { emits: ["click"], template: "<button @click=\"$emit('click')\"><slot /></button>" },
  "v-spacer": { template: "<span />" },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": { emits: ["click"], template: "<li @click=\"$emit('click')\"><slot /></li>" },
  "v-list-item-title": { template: "<span><slot /></span>" },
  "v-list-item-subtitle": { template: "<span><slot /></span>" },
  "v-icon": { template: "<i />" },
  "v-dialog": { template: "<div><slot /></div>" },
  MaraudersInkPolygon: { props: ["points", "canvasW", "canvasH", "seedKey", "label", "fill"], template: "<g data-testid='marauders-ink-polygon' />" },
};

async function mountEditor(props = {}) {
  const wrapper = mount(DoorZoneEditor, {
    props: {
      rooms,
      zones: [],
      floorPlanUrl: "/floor.png",
      canvasW: 1000,
      canvasH: 500,
      fpMpp: 0.02,
      ...props,
    },
    global: { stubs },
    attachTo: document.body,
  });

  const container = wrapper.find(".cc-spatial-editor").element;
  container.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500 });
  const img = wrapper.find("img").element;
  Object.defineProperty(img, "naturalWidth", { configurable: true, value: 1000 });
  Object.defineProperty(img, "naturalHeight", { configurable: true, value: 500 });
  Object.defineProperty(img, "offsetWidth", { configurable: true, value: 1000 });
  Object.defineProperty(img, "offsetHeight", { configurable: true, value: 500 });
  Object.defineProperty(img, "offsetLeft", { configurable: true, value: 0 });
  Object.defineProperty(img, "offsetTop", { configurable: true, value: 0 });
  await wrapper.find("img").trigger("load");
  await nextTick();
  return wrapper;
}

async function drawTriangle(wrapper) {
  const svg = wrapper.find("svg");
  await svg.trigger("click", { clientX: 100, clientY: 100, detail: 1 });
  await nextTick();
  await svg.trigger("click", { clientX: 300, clientY: 100, detail: 1 });
  await nextTick();
  await svg.trigger("click", { clientX: 300, clientY: 200, detail: 1 });
  await nextTick();
}

async function drawDirection(wrapper) {
  wrapper.vm.activeTool = "direction";
  await nextTick();
  const hit = wrapper.find(".door-zone-direction-hit");
  hit.element.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500 });
  await hit.trigger("click", { clientX: 200, clientY: 150 });
  await nextTick();
  await hit.trigger("click", { clientX: 400, clientY: 150 });
  await nextTick();
}

describe("DoorZoneEditor", () => {
  it("uses the shared floor-plan background treatment", async () => {
    const wrapper = await mountEditor();

    expect(wrapper.find("img").classes()).toContain("cc-floor-plan-background-image");
  });

  beforeEach(() => {
    createTransitZone.mockReset().mockResolvedValue({ id: "zone-1" });
    updateTransitZone.mockReset().mockResolvedValue({ id: "zone-1" });
    deleteTransitZone.mockReset().mockResolvedValue(null);
    notifySuccess.mockReset();
    notifyError.mockReset();
    showConfirm.mockReset().mockResolvedValue(true);
  });

  it("draws polygon and direction before creating a normalized transit zone", async () => {
    const wrapper = await mountEditor();
    wrapper.vm.form.name = "Bathroom door";
    wrapper.vm.form.inside_room_id = 1;
    wrapper.vm.form.outside_room_id = 2;

    await drawTriangle(wrapper);
    await drawDirection(wrapper);
    await wrapper.vm.saveZone();
    await flushPromises();

    expect(createTransitZone).toHaveBeenCalledWith({
      name: "Bathroom door",
      kind: "door",
      polygon: [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]],
      inside_room_id: 1,
      outside_room_id: 2,
      direction_vec: [1, 0],
    });
    expect(wrapper.emitted("saved")).toHaveLength(1);
  });

  it("loads an existing zone and saves with PATCH", async () => {
    const zone = {
      id: "zone-1",
      name: "Old door",
      kind: "threshold",
      polygon: [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]],
      inside_room_id: 1,
      outside_room_id: 2,
      direction_vec: [1, 0],
    };
    const wrapper = await mountEditor({ zones: [zone] });

    wrapper.vm.loadZone(zone);
    wrapper.vm.form.name = "Updated door";
    await wrapper.vm.saveZone();
    await flushPromises();

    expect(updateTransitZone).toHaveBeenCalledWith("zone-1", expect.objectContaining({
      name: "Updated door",
      kind: "threshold",
      inside_room_id: 1,
      outside_room_id: 2,
      direction_vec: [1, 0],
    }));
  });

  it("confirms before deleting a zone", async () => {
    const zone = { id: "zone-1", name: "Bathroom door", inside_room_id: 1, outside_room_id: 2 };
    const wrapper = await mountEditor({ zones: [zone] });

    await wrapper.vm.deleteZone(zone);
    await flushPromises();

    expect(showConfirm).toHaveBeenCalledWith(
      "Delete Door Zone",
      'Delete "Bathroom door"? Transit detection for this doorway will stop.'
    );
    expect(deleteTransitZone).toHaveBeenCalledWith("zone-1");
    expect(wrapper.emitted("deleted")).toHaveLength(1);
  });

  it("does not save while floor-plan scale is unset", async () => {
    const wrapper = await mountEditor({ fpMpp: null });
    wrapper.vm.form.name = "Bathroom door";
    wrapper.vm.form.inside_room_id = 1;
    wrapper.vm.form.outside_room_id = 2;
    wrapper.vm.polygon = [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]];
    wrapper.vm.directionStart = [0.2, 0.3];
    wrapper.vm.directionEnd = [0.4, 0.3];

    await wrapper.vm.saveZone();

    expect(wrapper.text()).toContain("Set the floor-plan scale first");
    expect(createTransitZone).not.toHaveBeenCalled();
  });
});
