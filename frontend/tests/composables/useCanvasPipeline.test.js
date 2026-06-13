import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, h } from "vue";

const mocks = vi.hoisted(() => ({
  api: {
    getStepTypes: vi.fn(),
    getRuleSteps: vi.fn(),
    getRuleEdges: vi.fn(),
    updateRuleStepPosition: vi.fn(),
    replaceRuleEdges: vi.fn(),
    deleteRuleStep: vi.fn(),
    batchUpdateStepPositions: vi.fn(),
  },
  notify: {
    error: vi.fn(),
  },
}));

vi.mock("@/services/api.js", () => ({
  api: mocks.api,
}));

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: mocks.notify }),
}));

import { POSITION_SAVE_DEBOUNCE_MS, useCanvasPipeline } from "../../src/composables/useCanvasPipeline.js";

const STEP = {
  id: 10,
  step_type: "condition",
  label: "check_motion",
  enabled: true,
  config_json: { expression: "motion == true" },
  position_x: 120,
  position_y: 80,
};

const EDGE = {
  id: 99,
  rule_id: 42,
  source_step_id: 10,
  source_port: "true",
  target_step_id: 11,
  target_port: "main",
};

function mountComposable(ruleId = 42) {
  let result;
  const Wrapper = defineComponent({
    setup() {
      result = useCanvasPipeline(ruleId);
      return () => h("div");
    },
  });
  const wrapper = mount(Wrapper);
  return { result, wrapper };
}

async function settleInitialLoad() {
  await flushPromises();
  await flushPromises();
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.api.getStepTypes.mockResolvedValue([
    { type_name: "condition", output_ports: ["true", "false"] },
  ]);
  mocks.api.getRuleSteps.mockResolvedValue([STEP]);
  mocks.api.getRuleEdges.mockResolvedValue([EDGE]);
  mocks.api.updateRuleStepPosition.mockResolvedValue({ ...STEP });
  mocks.api.replaceRuleEdges.mockResolvedValue([]);
  mocks.api.deleteRuleStep.mockResolvedValue(null);
  mocks.api.batchUpdateStepPositions.mockResolvedValue({ updated: 1 });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useCanvasPipeline", () => {
  it("loads steps and edges and transforms them to Vue Flow format", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    expect(result.state.nodes).toEqual([
      expect.objectContaining({
        id: "10",
        type: "step",
        position: { x: 120, y: 80 },
        data: expect.objectContaining({
          step: STEP,
          outputPorts: ["true", "false"],
        }),
      }),
    ]);
    expect(result.state.edges).toEqual([
      expect.objectContaining({
        id: "99",
        source: "10",
        sourceHandle: "true",
        target: "11",
        targetHandle: "main",
        label: "true",
      }),
    ]);
  });

  it("saves position after drag-stop with debounce", async () => {
    vi.useFakeTimers();
    const { result } = mountComposable();
    await settleInitialLoad();

    result.actions.onNodeDragStop({
      node: { id: "10", position: { x: 300, y: 220 } },
    });

    await vi.advanceTimersByTimeAsync(POSITION_SAVE_DEBOUNCE_MS - 1);
    expect(mocks.api.updateRuleStepPosition).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    await flushPromises();

    expect(mocks.api.updateRuleStepPosition).toHaveBeenCalledWith(42, 10, {
      position_x: 300,
      position_y: 220,
    });
  });

  it("sets error state on API failure", async () => {
    mocks.api.getRuleSteps.mockRejectedValue(new Error("steps failed"));
    const { result } = mountComposable();
    await settleInitialLoad();

    expect(result.state.error).toBe("steps failed");
    expect(result.state.loading).toBe(false);
  });

  it("refreshNodeData updates node data without full reload", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    result.actions.refreshNodeData({ ...STEP, label: "updated_check" });

    expect(result.state.nodes[0].data.step.label).toBe("updated_check");
    expect(mocks.api.getRuleSteps).toHaveBeenCalledTimes(1);
  });

  it("addEdge calls replaceRuleEdges with new edge appended", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    await result.actions.addEdge({
      source: "10",
      sourceHandle: "false",
      target: "12",
      targetHandle: "main",
    });

    expect(mocks.api.replaceRuleEdges).toHaveBeenCalledWith(42, [
      {
        source_step_id: 10,
        source_port: "true",
        target_step_id: 11,
        target_port: "main",
      },
      {
        source_step_id: 10,
        source_port: "false",
        target_step_id: 12,
        target_port: "main",
      },
    ]);
    expect(mocks.api.getRuleSteps).toHaveBeenCalledTimes(2);
  });

  it("addEdge shows error notification when API returns 422", async () => {
    mocks.api.replaceRuleEdges.mockRejectedValue(new Error("HTTP 422"));
    const { result } = mountComposable();
    await settleInitialLoad();

    await result.actions.addEdge({
      source: "10",
      sourceHandle: "false",
      target: "12",
      targetHandle: "main",
    });

    expect(mocks.notify.error).toHaveBeenCalledWith("Connection invalid: HTTP 422");
  });

  it("addEdge rejects self-loop connection without API call", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    await result.actions.addEdge({
      source: "10",
      sourceHandle: "false",
      target: "10",
      targetHandle: "main",
    });

    expect(mocks.api.replaceRuleEdges).not.toHaveBeenCalled();
    expect(mocks.notify.error).toHaveBeenCalledWith("Cannot connect a step to itself.");
  });

  it("addEdge allows fan-out: one source port to multiple targets", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    // An edge 10:true -> 11 already exists in the fixture. Connecting the same
    // port to a different target (12) is a valid fan-out and must persist.
    await result.actions.addEdge({
      source: "10",
      sourceHandle: "true",
      target: "12",
      targetHandle: "main",
    });

    expect(mocks.api.replaceRuleEdges).toHaveBeenCalledTimes(1);
    expect(mocks.notify.error).not.toHaveBeenCalled();
  });

  it("addEdge rejects an exact duplicate edge without API call", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    // Same source port AND same target as the existing fixture edge.
    await result.actions.addEdge({
      source: "10",
      sourceHandle: "true",
      target: "11",
      targetHandle: "main",
    });

    expect(mocks.api.replaceRuleEdges).not.toHaveBeenCalled();
    expect(mocks.notify.error).toHaveBeenCalledWith(
      "These steps are already connected on this port.",
    );
  });

  it("addEdge rejects invalid source handles without API call", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    await result.actions.addEdge({
      source: "10",
      sourceHandle: "maybe",
      target: "12",
      targetHandle: "main",
    });

    expect(mocks.api.replaceRuleEdges).not.toHaveBeenCalled();
    expect(mocks.notify.error).toHaveBeenCalledWith('Output port "maybe" is not valid for this step.');
  });

  it("addEdge rejects non-main target handles without API call", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    await result.actions.addEdge({
      source: "10",
      sourceHandle: "false",
      target: "12",
      targetHandle: "alt",
    });

    expect(mocks.api.replaceRuleEdges).not.toHaveBeenCalled();
    expect(mocks.notify.error).toHaveBeenCalledWith("Pipeline steps only accept connections on the main input.");
  });

  it("removeEdge calls replaceRuleEdges without the removed edge", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    await result.actions.removeEdge("99");

    expect(mocks.api.replaceRuleEdges).toHaveBeenCalledWith(42, []);
    expect(mocks.api.getRuleSteps).toHaveBeenCalledTimes(2);
  });

  it("removeNode calls the existing deleteRuleStep api method", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    await result.actions.removeNode(10);

    expect(mocks.api.deleteRuleStep).toHaveBeenCalledWith(42, 10);
    expect(mocks.api.getRuleSteps).toHaveBeenCalledTimes(2);
  });

  it("batchSavePositions calls batchUpdateStepPositions with correct payload", async () => {
    const { result } = mountComposable();
    await settleInitialLoad();

    await result.actions.batchSavePositions([
      { id: "10", position: { x: 300, y: 220 } },
      { id: "11", position: { x: 620, y: 220 } },
    ]);

    expect(mocks.api.batchUpdateStepPositions).toHaveBeenCalledWith(42, [
      { step_id: 10, position_x: 300, position_y: 220 },
      { step_id: 11, position_x: 620, position_y: 220 },
    ]);
  });
});
