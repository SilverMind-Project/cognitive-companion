import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import GateEditorDialog from "@/components/routines/GateEditorDialog.vue";

// Stub AppDialog so we can check props passed to it
const AppDialogStub = {
  name: "AppDialog",
  template: `<div class="app-dialog-stub" :class="size">
    <slot />
    <button class="close-btn" @click="$emit('update:modelValue', false)">Close</button>
  </div>`,
  props: ["modelValue", "size", "icon", "label", "title", "confirmLabel"],
};

function mountGateEditorDialog(props) {
  return mount(GateEditorDialog, {
    props: {
      modelValue: true,
      gate: {},
      ...props,
    },
    global: {
      stubs: {
        AppDialog: AppDialogStub,
      }
    }
  });
}

describe("GateEditorDialog", () => {
  it("renders inside an xl AppDialog", () => {
    const wrapper = mountGateEditorDialog({});
    const appDialog = wrapper.findComponent(AppDialogStub);
    expect(appDialog.exists()).toBe(true);
    expect(appDialog.props("size")).toBe("xl");
    expect(appDialog.props("title")).toBe("Edit Vision Logic");
  });

  it("emits update:modelValue when closed", async () => {
    const wrapper = mountGateEditorDialog({});
    await wrapper.find(".close-btn").trigger("click");
    expect(wrapper.emitted("update:modelValue")[0]).toEqual([false]);
  });
});
