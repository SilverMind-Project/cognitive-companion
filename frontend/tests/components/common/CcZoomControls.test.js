import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import CcZoomControls from "@/components/common/CcZoomControls.vue";

const stubs = {
  "v-btn": {
    props: ["icon", "disabled", "title", "size"],
    emits: ["click"],
    template: "<button :title=\"title\" :disabled=\"disabled\" :data-icon=\"icon\" :data-size=\"size\" @click=\"$emit('click')\"><slot /></button>",
  },
  "v-chip": { template: "<span class=\"cc-zoom-pct\"><slot /></span>" },
};

function mountControls(props = {}) {
  return mount(CcZoomControls, {
    props: { zoom: 1, panX: 0, panY: 0, ...props },
    global: { stubs },
  });
}

describe("CcZoomControls", () => {
  it("uses x-small controls and displays zoom percentage", () => {
    const wrapper = mountControls({ zoom: 1.25 });
    const buttons = wrapper.findAll("button");

    expect(buttons).toHaveLength(3);
    expect(buttons.every((button) => button.attributes("data-size") === "x-small")).toBe(true);
    expect(wrapper.text()).toContain("125%");
  });

  it("emits zoom and reset actions", async () => {
    const wrapper = mountControls({ zoom: 1.5, panX: 4 });
    const buttons = wrapper.findAll("button");

    await buttons[0].trigger("click");
    await buttons[1].trigger("click");
    await buttons[2].trigger("click");

    expect(wrapper.emitted("zoom-in")).toHaveLength(1);
    expect(wrapper.emitted("zoom-out")).toHaveLength(1);
    expect(wrapper.emitted("reset")).toHaveLength(1);
  });

  it("supports optional fit and fullscreen actions", async () => {
    const wrapper = mountControls({ showFit: true, showFullscreen: true });
    const buttons = wrapper.findAll("button");

    await buttons[3].trigger("click");
    await buttons[4].trigger("click");

    expect(wrapper.emitted("fit")).toHaveLength(1);
    expect(wrapper.emitted("fullscreen")).toHaveLength(1);
  });

  it("disables reset within tolerance", () => {
    const wrapper = mountControls({ zoom: 1.005, panX: 0.5, panY: -0.5 });
    expect(wrapper.find("button[title='Reset zoom and pan']").attributes("disabled")).toBeDefined();
  });
});
