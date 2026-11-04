import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const api = vi.hoisted(() => ({
  getMedicationSchedule: vi.fn(),
  createMedicationEntry: vi.fn(),
  updateMedicationEntry: vi.fn(),
  deleteMedicationEntry: vi.fn(),
}));
vi.mock("@/services/api.js", () => ({ api }));
vi.mock("@/composables/useNotify.js", async (original) => ({
  ...(await original()),
  useNotify: () => ({ notify: vi.fn() }),
}));

import MedicationScheduleCard from "@/components/person/MedicationScheduleCard.vue";

const slot = { template: "<div><slot /><slot name='append' /></div>" };
const AppDialog = {
  name: "AppDialog",
  props: ["modelValue", "title", "confirmDisabled"],
  emits: ["confirm", "update:modelValue"],
  template: "<div v-if='modelValue' data-testid='dialog'>{{ title }}<slot /></div>",
};
const stubs = {
  AppDialog,
  "v-alert": slot,
  "v-btn": { template: "<button v-bind='$attrs'><slot /></button>" },
  "v-card": slot,
  "v-card-actions": slot,
  "v-card-text": slot,
  "v-card-title": slot,
  "v-chip": slot,
  "v-chip-group": slot,
  "v-dialog": slot,
  "v-list": slot,
  "v-list-item": slot,
  "v-list-item-subtitle": slot,
  "v-list-item-title": slot,
  "v-skeleton-loader": slot,
  "v-spacer": slot,
  "v-text-field": { template: "<input />" },
};

const ENTRY = { id: 1, label: "Morning tablets", dose_time: "08:00", days_of_week: [0, 2] };

async function mountCard(items = [ENTRY]) {
  api.getMedicationSchedule.mockResolvedValue({ items, total: items.length });
  const wrapper = mount(MedicationScheduleCard, {
    props: { personId: "rose" },
    global: { stubs },
  });
  await flushPromises();
  return wrapper;
}

describe("MedicationScheduleCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists each dose with its time and days", async () => {
    const wrapper = await mountCard();
    expect(wrapper.text()).toContain("Morning tablets");
    expect(wrapper.text()).toContain("8:00 AM · Mon, Wed");
  });

  it("invites a caregiver to add the first dose", async () => {
    const wrapper = await mountCard([]);
    expect(wrapper.text()).toContain("No doses scheduled");
  });

  it("needs a name and at least one day before saving", async () => {
    const wrapper = await mountCard();
    wrapper.vm.openAdd();
    await flushPromises();
    const dialog = wrapper.findComponent({ name: "AppDialog" });
    expect(dialog.props("confirmDisabled")).toBe(true);

    wrapper.vm.form.label = "Evening";
    await flushPromises();
    expect(dialog.props("confirmDisabled")).toBe(false);

    wrapper.vm.form.days_of_week = [];
    await flushPromises();
    expect(dialog.props("confirmDisabled")).toBe(true);
  });

  it("saves an edit against the entry being edited", async () => {
    api.updateMedicationEntry.mockResolvedValue(ENTRY);
    const wrapper = await mountCard();
    wrapper.vm.openEdit(ENTRY);
    wrapper.vm.form.label = "  Heart tablets  ";
    await wrapper.vm.save();
    expect(api.updateMedicationEntry).toHaveBeenCalledWith("rose", 1, {
      label: "Heart tablets",
      dose_time: "08:00",
      days_of_week: [0, 2],
    });
    expect(wrapper.vm.dialogOpen).toBe(false);
  });
});
