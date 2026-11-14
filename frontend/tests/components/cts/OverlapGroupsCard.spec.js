import { describe, expect, it, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";
import OverlapGroupsCard from "@/components/cts/OverlapGroupsCard.vue";

const createOverlapGroup = vi.fn();
const deleteOverlapGroup = vi.fn();
const notifySuccess = vi.fn();
const notifyError = vi.fn();
const showConfirm = vi.fn();

vi.mock("@/services/cts.js", () => ({
  cts: {
    createOverlapGroup: (...args) => createOverlapGroup(...args),
    deleteOverlapGroup: (...args) => deleteOverlapGroup(...args),
  },
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({
    notify: Object.assign(vi.fn(), { success: notifySuccess, error: notifyError }),
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

const modelStub = (tag) => ({
  props: ["modelValue"],
  emits: ["update:modelValue"],
  template: `<${tag} />`,
});

const stubs = {
  "v-card": { template: "<section><slot /></section>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-subtitle": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-divider": { template: "<hr />" },
  "v-spacer": { template: "<span />" },
  "v-list": { template: "<ul><slot /></ul>" },
  "v-list-item": { template: "<li><slot /><slot name='append' /></li>" },
  "v-list-item-title": { template: "<span><slot /></span>" },
  "v-list-item-subtitle": { template: "<span><slot /></span>" },
  "v-icon": { template: "<i />" },
  "v-dialog": { template: "<div><slot /></div>" },
  "v-text-field": modelStub("input"),
  "v-select": modelStub("select"),
  "v-btn": {
    props: ["disabled"],
    emits: ["click"],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
};

const cameras = [
  { id: "living-room-2", name: "Living room" },
  { id: "side-corridor", name: "Side corridor" },
  { id: "kitchen-cam-1", name: "Kitchen" },
];

function mountCard(groups = []) {
  return mount(OverlapGroupsCard, { props: { groups, cameras }, global: { stubs } });
}

async function fill(wrapper, name, cameraIds) {
  const [nameField] = wrapper.findAllComponents(stubs["v-text-field"]);
  const [cameraField] = wrapper.findAllComponents(stubs["v-select"]);
  nameField.vm.$emit("update:modelValue", name);
  cameraField.vm.$emit("update:modelValue", cameraIds);
  await flushPromises();
}

describe("OverlapGroupsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists each group with its cameras", () => {
    const wrapper = mountCard([
      { id: 3, name: "Living room", camera_ids: ["living-room-2", "side-corridor"] },
    ]);

    const row = wrapper.find("[data-testid='overlap-group-3']");
    expect(row.text()).toContain("Living room");
    expect(row.text()).toContain("living-room-2, side-corridor");
  });

  it("explains the empty state", () => {
    expect(mountCard().text()).toContain("No overlap groups");
  });

  it("does not create a group with fewer than two cameras", async () => {
    const wrapper = mountCard();
    await fill(wrapper, "Living room", ["living-room-2"]);

    const create = wrapper.find("[data-testid='overlap-group-create']");
    expect(create.attributes("disabled")).toBeDefined();
  });

  it("creates a group and asks the parent to reload", async () => {
    createOverlapGroup.mockResolvedValue({ id: 4 });
    const wrapper = mountCard();
    await fill(wrapper, "  Living room ", ["living-room-2", "side-corridor"]);

    await wrapper.find("[data-testid='overlap-group-create']").trigger("click");
    await flushPromises();

    expect(createOverlapGroup).toHaveBeenCalledWith({
      name: "Living room",
      camera_ids: ["living-room-2", "side-corridor"],
    });
    expect(wrapper.emitted("changed")).toHaveLength(1);
    expect(notifySuccess).toHaveBeenCalled();
  });

  it("deletes only after confirmation", async () => {
    const group = { id: 5, name: "Living room", camera_ids: ["living-room-2", "side-corridor"] };
    const wrapper = mountCard([group]);
    const deleteButton = () => wrapper.find("[data-testid='overlap-group-5'] button");

    showConfirm.mockResolvedValueOnce(false);
    await deleteButton().trigger("click");
    await flushPromises();
    expect(deleteOverlapGroup).not.toHaveBeenCalled();

    showConfirm.mockResolvedValueOnce(true);
    deleteOverlapGroup.mockResolvedValue(null);
    await deleteButton().trigger("click");
    await flushPromises();
    expect(deleteOverlapGroup).toHaveBeenCalledWith(5);
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("reports a failed create without emitting a change", async () => {
    createOverlapGroup.mockRejectedValue(new Error("upstream down"));
    const wrapper = mountCard();
    await fill(wrapper, "Living room", ["living-room-2", "side-corridor"]);

    await wrapper.find("[data-testid='overlap-group-create']").trigger("click");
    await flushPromises();

    expect(notifyError).toHaveBeenCalledWith("upstream down");
    expect(wrapper.emitted("changed")).toBeUndefined();
  });
});
