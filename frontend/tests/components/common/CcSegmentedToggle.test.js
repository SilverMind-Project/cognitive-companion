import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import CcSegmentedToggle from "@/components/common/CcSegmentedToggle.vue";

// Stub v-btn so we can read the props the component computes (variant/color)
// and drive its click without installing Vuetify.
// Root is a real <button>; the component's @click is attached to it via
// fallthrough, so a native click bubbles to it once (no manual re-emit, which
// would double-fire alongside the bubble).
const vBtn = {
  name: "v-btn",
  template: "<button><slot /></button>",
  props: ["size", "variant", "color", "prependIcon", "ariaPressed"],
};

function mountToggle(props) {
  return mount(CcSegmentedToggle, {
    props,
    global: { stubs: { "v-btn": vBtn } },
  });
}

const OPTIONS = [
  { value: "table", label: "Table", icon: "mdi-table" },
  { value: "timeline", label: "Timeline" },
];

describe("CcSegmentedToggle", () => {
  it("renders one button per option with its label", () => {
    const wrapper = mountToggle({ modelValue: "table", options: OPTIONS });
    const btns = wrapper.findAllComponents(vBtn);
    expect(btns).toHaveLength(2);
    expect(btns[0].text()).toBe("Table");
    expect(btns[1].text()).toBe("Timeline");
  });

  it("renders the selected option as flat+color and the rest as outlined", () => {
    const wrapper = mountToggle({ modelValue: "table", options: OPTIONS });
    const [selected, other] = wrapper.findAllComponents(vBtn);
    expect(selected.props("variant")).toBe("flat");
    expect(selected.props("color")).toBe("primary");
    expect(other.props("variant")).toBe("outlined");
    expect(other.props("color")).toBeUndefined();
  });

  it("honors a custom active color", () => {
    const wrapper = mountToggle({ modelValue: "table", options: OPTIONS, color: "secondary" });
    expect(wrapper.findAllComponents(vBtn)[0].props("color")).toBe("secondary");
  });

  it("emits update:modelValue with the clicked option's value", async () => {
    const wrapper = mountToggle({ modelValue: "table", options: OPTIONS });
    await wrapper.findAllComponents(vBtn)[1].trigger("click");
    expect(wrapper.emitted("update:modelValue")).toEqual([["timeline"]]);
  });

  it("passes the option icon through to the button", () => {
    const wrapper = mountToggle({ modelValue: "table", options: OPTIONS });
    const [withIcon, withoutIcon] = wrapper.findAllComponents(vBtn);
    expect(withIcon.props("prependIcon")).toBe("mdi-table");
    expect(withoutIcon.props("prependIcon")).toBeUndefined();
  });
});
