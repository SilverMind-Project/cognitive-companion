import { reactive, toValue, watch } from "vue";
import { api } from "@/services/api.js";
import { requireNotify } from "@/composables/useNotify.js";

/** A person's medication schedule: the list, and the changes a caregiver can make to it. */
export function useMedicationSchedule(personId, { notify } = {}) {
  requireNotify("useMedicationSchedule", notify);

  const state = reactive({ entries: [], loading: false, saving: false, error: null });

  async function load() {
    state.loading = true;
    state.error = null;
    try {
      state.entries = (await api.getMedicationSchedule(toValue(personId))).items;
    } catch (e) {
      state.error = e.message;
    } finally {
      state.loading = false;
    }
  }

  async function change(request, message) {
    state.saving = true;
    try {
      await request();
      await load();
      notify(message);
      return true;
    } catch (e) {
      notify(e.message, "error");
      return false;
    } finally {
      state.saving = false;
    }
  }

  const addDose = (dose) =>
    change(() => api.createMedicationEntry(toValue(personId), dose), "Dose added");

  const updateDose = (entryId, dose) =>
    change(() => api.updateMedicationEntry(toValue(personId), entryId, dose), "Dose updated");

  const removeDose = (entryId) =>
    change(() => api.deleteMedicationEntry(toValue(personId), entryId), "Dose removed");

  watch(() => toValue(personId), load, { immediate: true });

  return { state, actions: { load, addDose, updateDose, removeDose } };
}
