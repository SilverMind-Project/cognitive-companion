import { ref } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";

/** Dependency dialog state and CRUD for a rule's dependency list. */
export function useRuleDependencies(ruleId, { onChanged } = {}) {
  const { notify } = useNotify();

  const depDialog = ref(false);
  const depForm = ref({ parent_rule_id: 0, lookback_minutes: 30, require_success: true });

  async function addDep() {
    try {
      await api.addRuleDep(ruleId.value, depForm.value);
      depDialog.value = false;
      await onChanged?.();
      notify("Dependency added");
    } catch (e) {
      notify(e.message, "error");
    }
  }

  async function deleteDep(depId) {
    try {
      await api.deleteRuleDep(ruleId.value, depId);
      await onChanged?.();
    } catch (e) {
      notify(e.message, "error");
    }
  }

  return {
    depDialog,
    depForm,
    addDep,
    deleteDep,
  };
}
