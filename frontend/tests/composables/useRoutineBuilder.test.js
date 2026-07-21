/**
 * Tests for useRoutineBuilder composable.
 *
 * Verifies:
 * - load() populates state.routine and state.steps
 * - addStep() appends a new step with the next ord
 * - removeStep() removes a step and re-indexes ords
 * - moveStep() swaps steps and re-indexes
 * - updateStep() merges fields without mutation
 * - saveSteps() calls replaceRoutineSteps() with current steps
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, h } from "vue";

const mockApi = vi.hoisted(() => ({
  getRoutine: vi.fn(),
  updateRoutine: vi.fn(),
  replaceRoutineSteps: vi.fn(),
  testRunRoutine: vi.fn(),
}));

vi.mock("@/services/api.js", () => ({ api: mockApi }));
vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn() } }),
}));

import { useRoutineBuilder } from "../../src/composables/useRoutineBuilder.js";

function mountComposable() {
  let result;
  const Wrapper = defineComponent({
    setup() {
      result = useRoutineBuilder();
      return () => h("div");
    },
  });
  mount(Wrapper);
  return result;
}

const ROUTINE = {
  id: 1,
  name: "Make Tea",
  person_id: "resident-1",
  is_enabled: true,
  step_count: 2,
};

const STEPS = [
  {
    id: 10,
    routine_id: 1,
    ord: 0,
    prompt_template: "Boil water.",
    completion_gate: { kinds: ["response"] },
    is_safety_critical: false,
  },
  {
    id: 11,
    routine_id: 1,
    ord: 1,
    prompt_template: "Pour water.",
    completion_gate: { kinds: ["response"] },
    is_safety_critical: false,
  },
];

describe("useRoutineBuilder", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockApi.getRoutine.mockResolvedValue({ routine: ROUTINE, steps: STEPS });
    mockApi.replaceRoutineSteps.mockResolvedValue({ routine: ROUTINE, steps: STEPS });
  });

  it("load populates routine and steps", async () => {
    const { state, actions } = mountComposable();
    await actions.load(1);
    await flushPromises();
    expect(state.routine.name).toBe("Make Tea");
    expect(state.steps).toHaveLength(2);
    expect(state.steps[0].ord).toBe(0);
    expect(state.steps[1].ord).toBe(1);
  });

  it("addStep appends with next ord", async () => {
    const { state, actions } = mountComposable();
    await actions.load(1);
    await flushPromises();
    actions.addStep();
    expect(state.steps).toHaveLength(3);
    expect(state.steps[2].ord).toBe(2);
    expect(state.steps[2].prompt_template).toBe("");
  });

  it("removeStep re-indexes ords", async () => {
    const { state, actions } = mountComposable();
    await actions.load(1);
    await flushPromises();
    actions.removeStep(0);
    expect(state.steps).toHaveLength(1);
    expect(state.steps[0].ord).toBe(0);
    expect(state.steps[0].prompt_template).toBe("Pour water.");
  });

  it("moveStep swaps positions and re-indexes", async () => {
    const { state, actions } = mountComposable();
    await actions.load(1);
    await flushPromises();
    actions.moveStep(0, 1);
    expect(state.steps[0].prompt_template).toBe("Pour water.");
    expect(state.steps[1].prompt_template).toBe("Boil water.");
    expect(state.steps[0].ord).toBe(0);
    expect(state.steps[1].ord).toBe(1);
  });

  it("updateStep merges fields", async () => {
    const { state, actions } = mountComposable();
    await actions.load(1);
    await flushPromises();
    actions.updateStep(0, { prompt_template: "Updated prompt." });
    expect(state.steps[0].prompt_template).toBe("Updated prompt.");
    expect(state.steps[0].ord).toBe(0);
  });

  it("saveSteps calls API with current steps", async () => {
    const { actions } = mountComposable();
    await actions.load(1);
    await flushPromises();
    await actions.saveSteps();
    await flushPromises();
    expect(mockApi.replaceRoutineSteps).toHaveBeenCalledWith(
      1,
      expect.arrayContaining([
        expect.objectContaining({ ord: 0 }),
        expect.objectContaining({ ord: 1 }),
      ]),
    );
  });
});
