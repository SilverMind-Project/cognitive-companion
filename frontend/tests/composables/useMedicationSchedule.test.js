import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { ref } from "vue";

const api = vi.hoisted(() => ({
  getMedicationSchedule: vi.fn(),
  createMedicationEntry: vi.fn(),
  updateMedicationEntry: vi.fn(),
  deleteMedicationEntry: vi.fn(),
}));
vi.mock("@/services/api.js", () => ({ api }));

import { useMedicationSchedule } from "@/composables/useMedicationSchedule.js";

const ENTRY = { id: 1, label: "Morning", dose_time: "08:00", days_of_week: [0] };

describe("useMedicationSchedule", () => {
  let notify;

  beforeEach(() => {
    vi.clearAllMocks();
    notify = vi.fn();
    api.getMedicationSchedule.mockResolvedValue({ items: [ENTRY], total: 1 });
  });

  it("loads the schedule, and reloads for a new person", async () => {
    const personId = ref("rose");
    const { state } = useMedicationSchedule(personId, { notify });
    await flushPromises();
    expect(state.entries).toEqual([ENTRY]);

    personId.value = "david";
    await flushPromises();
    expect(api.getMedicationSchedule).toHaveBeenLastCalledWith("david");
  });

  it("reports a failed load", async () => {
    api.getMedicationSchedule.mockRejectedValue(new Error("Offline"));
    const { state } = useMedicationSchedule(ref("rose"), { notify });
    await flushPromises();
    expect(state.error).toBe("Offline");
  });

  it("reloads after a change, because an edit can replace the entry", async () => {
    const { actions } = useMedicationSchedule(ref("rose"), { notify });
    await flushPromises();
    api.updateMedicationEntry.mockResolvedValue({ ...ENTRY, id: 2 });

    expect(await actions.updateDose(1, { label: "Heart" })).toBe(true);
    expect(api.updateMedicationEntry).toHaveBeenCalledWith("rose", 1, { label: "Heart" });
    expect(api.getMedicationSchedule).toHaveBeenCalledTimes(2);
    expect(notify).toHaveBeenCalledWith("Dose updated");
  });

  it("keeps the dialog's data when a save fails", async () => {
    const { actions } = useMedicationSchedule(ref("rose"), { notify });
    await flushPromises();
    api.createMedicationEntry.mockRejectedValue(new Error("Rejected"));

    expect(await actions.addDose({ label: "Morning" })).toBe(false);
    expect(notify).toHaveBeenCalledWith("Rejected", "error");
  });
});
