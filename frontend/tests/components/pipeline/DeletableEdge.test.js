import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";

const removeEdges = vi.fn();

vi.mock("@vue-flow/core", () => ({
  // BaseEdge renders nothing meaningful for this test.
  BaseEdge: { name: "BaseEdge", template: "<g />" },
  // EdgeLabelRenderer normally teleports; render the slot inline so we can
  // click the delete button.
  EdgeLabelRenderer: { name: "EdgeLabelRenderer", template: "<div><slot /></div>" },
  getSmoothStepPath: () => ["M0,0 L1,1", 5, 6],
  useVueFlow: () => ({ removeEdges }),
}));

import DeletableEdge from "@/components/pipeline/edges/DeletableEdge.vue";

function mountEdge(props = {}) {
  return mount(DeletableEdge, {
    props: {
      id: "edge-42",
      sourceX: 0,
      sourceY: 0,
      targetX: 10,
      targetY: 10,
      ...props,
    },
    global: {
      stubs: { "v-icon": { template: "<i><slot /></i>" } },
    },
  });
}

describe("DeletableEdge", () => {
  beforeEach(() => removeEdges.mockClear());

  it("removes the edge by id when the delete button is clicked", async () => {
    const wrapper = mountEdge();
    await wrapper.find(".cc-edge-delete").trigger("click");
    expect(removeEdges).toHaveBeenCalledWith(["edge-42"]);
  });

  it("does not remove a readonly edge", async () => {
    const wrapper = mountEdge({ data: { readonly: true } });
    await wrapper.find(".cc-edge-delete").trigger("click");
    expect(removeEdges).not.toHaveBeenCalled();
  });

  it("marks the button active when the edge is selected", () => {
    const wrapper = mountEdge({ selected: true });
    expect(wrapper.find(".cc-edge-delete").classes()).toContain("cc-edge-delete--active");
  });
});
