import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import RoutineStepCard from "@/components/routines/RoutineStepCard.vue";

// Mock child components that are not under test
vi.mock("@/components/routines/CompletionGateEditor.vue", () => ({
  default: {
    name: "CompletionGateEditor",
    template: '<div class="completion-gate-editor-stub"></div>',
    props: ["modelValue", "roomId"],
  }
}));

vi.mock("@/components/routines/ZonePicker.vue", () => ({
  default: {
    name: "ZonePicker",
    template: '<div class="zone-picker-stub"></div>',
    props: ["modelValue", "roomId", "label"],
  }
}));

vi.mock("@/components/routines/CameraPicker.vue", () => ({
  default: {
    name: "CameraPicker",
    template: '<div class="camera-picker-stub"></div>',
    props: ["modelValue", "label"],
  }
}));

const AppDialogStub = {
  name: "AppDialog",
  template: `<div class="app-dialog-stub" v-if="modelValue">
    <slot />
    <button class="confirm-btn" @click="$emit('confirm')">Save</button>
    <button class="cancel-btn" @click="$emit('cancel')">Cancel</button>
  </div>`,
  props: ["modelValue", "size", "icon", "label", "title", "confirmLabel"],
};

const vCard = {
  name: "v-card",
  template: '<div class="v-card-stub"><slot /></div>',
};

const vCardText = {
  name: "v-card-text",
  template: '<div class="v-card-text-stub"><slot /></div>',
};

const vBtn = {
  name: "v-btn",
  template: '<button class="v-btn-stub" @click="$emit(\'click\')"><slot /></button>',
};

const vTextarea = {
  name: "v-textarea",
  template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)"></textarea>',
  props: ["modelValue", "label"],
};

const vRow = { name: "v-row", template: "<div><slot /></div>" };
const vCol = { name: "v-col", template: "<div><slot /></div>" };
const vCheckbox = { name: "v-checkbox", template: "<div><slot /></div>" };
const vTextField = { name: "v-text-field", template: "<div><slot /></div>" };
const vExpansionPanels = { name: "v-expansion-panels", template: "<div><slot /></div>" };
const vExpansionPanel = { name: "v-expansion-panel", template: "<div><slot /></div>" };
const vExpansionPanelTitle = { name: "v-expansion-panel-title", template: "<div><slot /></div>" };
const vExpansionPanelText = { name: "v-expansion-panel-text", template: "<div><slot /></div>" };

function mountStepCard(props) {
  return mount(RoutineStepCard, {
    props: {
      step: {
        ord: 0,
        prompt_template: "Please do the thing",
        completion_gate: { kinds: ["response"] },
        skip_condition: null,
        camera_ids: ["cam1"],
        zone_id: "zone1",
        min_duration_s: null,
        step_timeout_s_override: null,
        max_step_attempts_override: null,
        is_safety_critical: false,
      },
      ...props,
    },
    global: {
      stubs: {
        AppDialog: AppDialogStub,
        "v-card": vCard,
        "v-card-text": vCardText,
        "v-btn": vBtn,
        "v-textarea": vTextarea,
        "v-row": vRow,
        "v-col": vCol,
        "v-checkbox": vCheckbox,
        "v-text-field": vTextField,
        "v-expansion-panels": vExpansionPanels,
        "v-expansion-panel": vExpansionPanel,
        "v-expansion-panel-title": vExpansionPanelTitle,
        "v-expansion-panel-text": vExpansionPanelText,
      }
    }
  });
}

describe("RoutineStepCard", () => {
  it("renders a concise summary of the step", () => {
    const wrapper = mountStepCard();
    expect(wrapper.text()).toContain("Please do the thing");
    expect(wrapper.text()).toContain("Gates: response");
    expect(wrapper.text()).toContain("Zone: zone1");
    expect(wrapper.text()).toContain("Cameras: cam1");
    // Dialog should be closed initially
    expect(wrapper.find(".app-dialog-stub").exists()).toBe(false);
  });

  it("opens the edit dialog when Edit Step is clicked", async () => {
    const wrapper = mountStepCard();
    const editBtn = wrapper.find("button.v-btn-stub");
    await editBtn.trigger("click");
    expect(wrapper.find(".app-dialog-stub").exists()).toBe(true);
  });

  it("emits update event when Save is clicked inside dialog", async () => {
    const wrapper = mountStepCard();
    // Open dialog
    await wrapper.find("button.v-btn-stub").trigger("click");
    // Modify text
    const textarea = wrapper.find("textarea");
    await textarea.setValue("New Prompt Text");
    // Click Save
    await wrapper.find(".confirm-btn").trigger("click");
    // Dialog closes
    expect(wrapper.find(".app-dialog-stub").exists()).toBe(false);
    // Emitted update
    expect(wrapper.emitted("update")[0][0].prompt_template).toBe("New Prompt Text");
  });

  it("does not emit update event if Cancel is clicked", async () => {
    const wrapper = mountStepCard();
    await wrapper.find("button.v-btn-stub").trigger("click");
    const textarea = wrapper.find("textarea");
    await textarea.setValue("New Prompt Text");
    await wrapper.find(".cancel-btn").trigger("click");
    expect(wrapper.emitted("update")).toBeFalsy();
  });
});
