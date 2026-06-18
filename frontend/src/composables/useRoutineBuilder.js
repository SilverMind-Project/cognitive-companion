import { reactive, readonly } from "vue";
import { api } from "@/services/api.js";
import { useNotify } from "@/composables/useNotify.js";

/**
 * State + actions for the Routine Builder view.
 * Manages a single routine with its ordered steps as a local edit buffer.
 * Persists steps via PUT /routines/{id}/steps.
 */
export function useRoutineBuilder() {
  const { notify } = useNotify();

  const state = reactive({
    loading: false,
    saving: false,
    testRunning: false,
    routine: null,
    steps: [],
    error: null,
  });

  async function load(routineId) {
    state.loading = true;
    state.error = null;
    try {
      const data = await api.getRoutine(routineId);
      state.routine = { ...data.routine };
      state.steps = data.steps.map((s) => ({ ...s }));
    } catch (err) {
      state.error = err.message || "Failed to load routine";
      notify.error(state.error);
    } finally {
      state.loading = false;
    }
  }

  async function saveRoutine(fields) {
    if (!state.routine) return;
    state.saving = true;
    try {
      const updated = await api.updateRoutine(state.routine.id, fields);
      Object.assign(state.routine, updated);
      notify.success("Routine saved.");
    } catch (err) {
      notify.error("Failed to save routine: " + (err.message || err));
    } finally {
      state.saving = false;
    }
  }

  async function saveSteps() {
    if (!state.routine) return;
    const validation = validateOrd(state.steps);
    if (!validation.ok) {
      notify.error(validation.error);
      return;
    }
    state.saving = true;
    try {
      const data = await api.replaceRoutineSteps(state.routine.id, state.steps);
      state.steps = data.steps.map((s) => ({ ...s }));
      Object.assign(state.routine, data.routine);
      notify.success("Steps saved.");
    } catch (err) {
      notify.error("Failed to save steps: " + (err.message || err));
    } finally {
      state.saving = false;
    }
  }

  function addStep() {
    const nextOrd = state.steps.length;
    state.steps.push({
      id: null,
      routine_id: state.routine?.id ?? null,
      ord: nextOrd,
      prompt_template: "",
      completion_gate: { kinds: ["response"] },
      skip_condition: null,
      camera_ids: null,
      zone_id: null,
      min_duration_s: null,
      step_timeout_s_override: null,
      max_step_attempts_override: null,
      is_safety_critical: false,
    });
  }

  function removeStep(index) {
    state.steps.splice(index, 1);
    reindex();
  }

  function moveStep(fromIndex, toIndex) {
    if (fromIndex < 0 || toIndex < 0) return;
    if (fromIndex >= state.steps.length || toIndex >= state.steps.length) return;
    const [moved] = state.steps.splice(fromIndex, 1);
    state.steps.splice(toIndex, 0, moved);
    reindex();
  }

  function updateStep(index, fields) {
    if (index < 0 || index >= state.steps.length) return;
    Object.assign(state.steps[index], fields);
  }

  async function testRun(surfaceId = null) {
    if (!state.routine) return;
    state.testRunning = true;
    try {
      const session = await api.testRunRoutine(state.routine.id, surfaceId ? { surface_id: surfaceId } : {});
      notify.success(`Test run started (session #${session.id}).`);
      return session;
    } catch (err) {
      notify.error("Failed to start test run: " + (err.message || err));
      return null;
    } finally {
      state.testRunning = false;
    }
  }

  function reindex() {
    state.steps.forEach((step, i) => {
      step.ord = i;
    });
  }

  function validateOrd(steps) {
    const ords = steps.map((s) => s.ord).sort((a, b) => a - b);
    for (let i = 0; i < ords.length; i++) {
      if (ords[i] !== i) {
        return { ok: false, error: `Step ord values must be contiguous from 0; found gap at ${ords[i]}` };
      }
    }
    return { ok: true };
  }

  return {
    state: readonly(state),
    actions: {
      load,
      saveRoutine,
      saveSteps,
      addStep,
      removeStep,
      moveStep,
      updateStep,
      testRun,
    },
  };
}
