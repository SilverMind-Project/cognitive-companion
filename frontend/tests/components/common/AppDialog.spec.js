import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import AppDialog from "@/components/common/AppDialog.vue";

// Mock DialogHeader and DialogFooter
vi.mock("@/components/common/DialogHeader.vue", () => ({
  default: {
    name: "DialogHeader",
    template: `<div class="dialog-header-stub">
      <span class="icon-prop">{{ icon }}</span>
      <span class="label-prop">{{ label }}</span>
      <span class="title-prop">{{ title }}</span>
      <button class="close-btn" @click="$emit('close')">Close</button>
    </div>`,
    props: ["icon", "label", "title", "closable"],
    emits: ["close"],
  },
}));

vi.mock("@/components/common/DialogFooter.vue", () => ({
  default: {
    name: "DialogFooter",
    template: `<div class="dialog-footer-stub">
      <span class="hint-prop">{{ hint }}</span>
      <span class="confirm-label-prop">{{ confirmLabel }}</span>
      <span class="cancel-label-prop">{{ cancelLabel }}</span>
      <button class="confirm-btn" @click="$emit('confirm')">Confirm</button>
      <button class="cancel-btn" @click="$emit('cancel')">Cancel</button>
    </div>`,
    props: [
      "hint",
      "cancelLabel",
      "confirmLabel",
      "confirmColor",
      "confirmLoading",
      "confirmDisabled",
    ],
    emits: ["cancel", "confirm"],
  },
}));

// Stands in for the tabbed body: renders every section slot so their content is assertable.
vi.mock("@/components/common/AppDialogSections.vue", () => ({
  default: {
    name: "AppDialogSections",
    props: ["sections", "modelValue", "compact"],
    emits: ["update:modelValue"],
    template: `<div class="sections-stub">
      <button v-for="s in sections" :key="s.key" :class="'nav-' + s.key"
        @click="$emit('update:modelValue', s.key)">{{ s.label }}</button>
      <div v-for="s in sections" :key="s.key" :class="'body-' + s.key">
        <slot :name="'section-' + s.key" />
      </div>
    </div>`,
  },
}));

const vDialog = {
  name: "v-dialog",
  template: `<div class="v-dialog-stub" :style="{ width: width }"><slot /></div>`,
  props: ["modelValue", "width", "maxWidth", "fullscreen", "scrollable", "persistent"],
};

const vDivider = { name: "v-divider", template: "<hr />", props: ["vertical"] };

const SECTIONS = [
  { key: "general", label: "General", icon: "mdi-cog" },
  { key: "geometry", label: "Geometry", icon: "mdi-angle-acute" },
];

const vCard = {
  name: "v-card",
  template: `<div class="v-card-stub"><slot /></div>`,
};

function mountAppDialog(props, slots = {}) {
  return mount(AppDialog, {
    props: {
      modelValue: true,
      icon: "mdi-alert",
      label: "My Label",
      title: "My Title",
      ...props,
    },
    slots,
    global: {
      stubs: {
        "v-dialog": vDialog,
        "v-card": vCard,
        "v-divider": vDivider,
      },
      mocks: {
        $vuetify: {
          display: {
            smAndDown: false,
          },
        },
      },
    },
  });
}

describe("AppDialog", () => {
  it("renders header (icon/label/title) and footer by default", () => {
    const wrapper = mountAppDialog({});
    expect(wrapper.find(".dialog-header-stub").exists()).toBe(true);
    expect(wrapper.find(".dialog-footer-stub").exists()).toBe(true);
    expect(wrapper.find(".icon-prop").text()).toBe("mdi-alert");
    expect(wrapper.find(".label-prop").text()).toBe("My Label");
    expect(wrapper.find(".title-prop").text()).toBe("My Title");
  });

  it("body slot renders", () => {
    const wrapper = mountAppDialog({}, { default: "<div>Hello Body</div>" });
    expect(wrapper.html()).toContain("Hello Body");
  });

  it("size maps to the expected width", () => {
    const sm = mountAppDialog({ size: "sm" });
    expect(sm.findComponent(vDialog).props("width")).toBe(480);

    const md = mountAppDialog({ size: "md" });
    expect(md.findComponent(vDialog).props("width")).toBe(720);

    const lg = mountAppDialog({ size: "lg" });
    expect(lg.findComponent(vDialog).props("width")).toBe(1080);

    const xl = mountAppDialog({ size: "xl" });
    expect(xl.findComponent(vDialog).props("width")).toBe(1440);
  });

  it("width prop overrides the preset", () => {
    const wrapper = mountAppDialog({ size: "xl", width: 600 });
    expect(wrapper.findComponent(vDialog).props("width")).toBe(600);
  });

  it("hideFooter hides the footer", () => {
    const wrapper = mountAppDialog({ hideFooter: true });
    expect(wrapper.find(".dialog-footer-stub").exists()).toBe(false);
  });

  it("confirm and close events fire", async () => {
    const wrapper = mountAppDialog({});
    await wrapper.find(".confirm-btn").trigger("click");
    expect(wrapper.emitted("confirm")).toBeTruthy();

    await wrapper.find(".close-btn").trigger("click");
    expect(wrapper.emitted("update:modelValue")[0]).toEqual([false]);
    expect(wrapper.emitted("cancel")).toBeTruthy();
    expect(wrapper.emitted("close")).toBeTruthy();
  });

  it("uses design tokens and cc-glass class, and bounds fullscreen to smAndDown", () => {
    const wrapper = mountAppDialog({});
    expect(wrapper.find(".cc-glass").exists()).toBe(true);
    expect(wrapper.findComponent(vDialog).props("fullscreen")).toBe(false);
  });

  it("is dismissible by default and persistent on request", () => {
    expect(mountAppDialog({}).findComponent(vDialog).props("persistent")).toBe(false);
    expect(mountAppDialog({ persistent: true }).findComponent(vDialog).props("persistent")).toBe(
      true,
    );
  });

  it("passes the confirm color to the footer", () => {
    const wrapper = mountAppDialog({ confirmColor: "error" });
    expect(wrapper.findComponent({ name: "DialogFooter" }).props("confirmColor")).toBe("error");
  });

  it("renders a sectioned body with one slot per section and a fixed height", () => {
    const wrapper = mountAppDialog(
      { size: "lg", sections: SECTIONS },
      {
        "section-general": "<div>General fields</div>",
        "section-geometry": "<div>Geometry fields</div>",
      },
    );
    const sections = wrapper.findComponent({ name: "AppDialogSections" });
    expect(sections.props("modelValue")).toBe("general");
    expect(wrapper.find(".body-general").text()).toBe("General fields");
    expect(wrapper.find(".body-geometry").text()).toBe("Geometry fields");
    expect(wrapper.find(".app-dialog-card--fixed").exists()).toBe(true);
  });

  it("tracks the active section and reports it for v-model:section", async () => {
    const wrapper = mountAppDialog({ sections: SECTIONS });
    await wrapper.find(".nav-geometry").trigger("click");

    expect(wrapper.emitted("update:section")[0]).toEqual(["geometry"]);
    expect(wrapper.findComponent({ name: "AppDialogSections" }).props("modelValue")).toBe(
      "geometry",
    );
  });

  it("follows a bound section, so a parent can jump to a section with errors", async () => {
    const wrapper = mountAppDialog({ sections: SECTIONS, section: "general" });
    await wrapper.setProps({ section: "geometry" });
    expect(wrapper.findComponent({ name: "AppDialogSections" }).props("modelValue")).toBe(
      "geometry",
    );
  });

  it("renders a split body: the aside form column beside the workspace", () => {
    const wrapper = mountAppDialog(
      { size: "lg" },
      { aside: "<div>Zone form</div>", default: "<div>Drawing canvas</div>" },
    );
    expect(wrapper.find(".app-dialog-aside").text()).toBe("Zone form");
    expect(wrapper.find(".app-dialog-main").text()).toBe("Drawing canvas");
    expect(wrapper.find(".app-dialog-card--fixed").exists()).toBe(true);
  });

  it("keeps the plain body for sm and md forms", () => {
    const wrapper = mountAppDialog({ size: "md" }, { default: "<div>Fields</div>" });
    expect(wrapper.find(".app-dialog-body").text()).toBe("Fields");
    expect(wrapper.find(".app-dialog-card--fixed").exists()).toBe(false);
  });
});
