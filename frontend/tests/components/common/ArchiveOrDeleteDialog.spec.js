import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ArchiveOrDeleteDialog from "@/components/common/ArchiveOrDeleteDialog.vue";

const stubs = {
  "v-dialog": { props: ["modelValue", "persistent"], template: "<div><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-divider": { template: "<hr />" },
  "v-avatar": { template: "<span><slot /></span>" },
  "v-icon": { template: "<i><slot /></i>" },
  "v-spacer": { template: "<span />" },
  "v-btn": {
    props: ["disabled", "loading", "color"],
    emits: ["click"],
    template: "<button :disabled='disabled' @click=\"$emit('click')\"><slot /></button>",
  },
};

function mountDialog(props = {}) {
  return mount(ArchiveOrDeleteDialog, {
    props: { modelValue: true, noun: "quiz", ...props },
    global: { stubs, mocks: { $vuetify: { display: { smAndDown: false } } } },
  });
}

function button(wrapper, label) {
  return wrapper.findAll("button").find((b) => b.text() === label);
}

describe("ArchiveOrDeleteDialog", () => {
  it("names the item and explains the permanent and reversible choices", () => {
    const wrapper = mountDialog({ name: "Morning facts" });
    expect(wrapper.text()).toContain('Delete "Morning facts"?');
    expect(wrapper.text()).toContain("removes this quiz permanently");
    expect(wrapper.text()).toContain("can be restored later");
  });

  it("falls back to the noun when the item has no title", () => {
    expect(mountDialog().text()).toContain("Delete this quiz?");
  });

  it("emits archive or delete, never both, and stays open on a stray click", async () => {
    const wrapper = mountDialog();
    expect(wrapper.findComponent(stubs["v-dialog"]).props("persistent")).toBe(true);

    await button(wrapper, "Archive instead").trigger("click");
    expect(wrapper.emitted("archive")).toHaveLength(1);
    expect(wrapper.emitted("delete")).toBeUndefined();

    await button(wrapper, "Delete permanently").trigger("click");
    expect(wrapper.emitted("delete")).toHaveLength(1);
  });

  it("blocks a second choice while the first is running", () => {
    const wrapper = mountDialog({ loading: true });
    expect(button(wrapper, "Archive instead").attributes("disabled")).toBeDefined();
  });
});
