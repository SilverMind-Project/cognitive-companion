import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import TrackingPanelHeader from "../../../src/components/tracking/TrackingPanelHeader.vue";

describe("TrackingPanelHeader", () => {
  it("renders panel copy below the workspace heading level", () => {
    const wrapper = mount(TrackingPanelHeader, {
      props: {
        title: "Signals",
        description: "Explore generated tracking signals.",
      },
    });

    expect(wrapper.get("h2").classes()).toContain("text-h5");
    expect(wrapper.text()).toContain("Explore generated tracking signals.");
  });

  it("renders panel actions when provided", () => {
    const wrapper = mount(TrackingPanelHeader, {
      props: { title: "Signals" },
      slots: { actions: "<button>Refresh</button>" },
    });

    expect(wrapper.get("button").text()).toBe("Refresh");
  });
});
