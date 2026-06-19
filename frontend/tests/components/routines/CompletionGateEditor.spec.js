import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  api: { getGatePresets: vi.fn(), createGateGraph: vi.fn() },
  notify: { error: vi.fn() },
}));

vi.mock("@/services/api.js", () => ({ api: mocks.api }));
vi.mock("@/composables/useNotify.js", () => ({ useNotify: () => ({ notify: mocks.notify }) }));

import CompletionGateEditor from "@/components/routines/CompletionGateEditor.vue";

const PRESETS = [
  { key: "generic_vlm_confirm", name: "Generic VLM Confirm", description: "d", summary: "poll -> llm -> verdict" },
  { key: "kettle_on_hob", name: "Kettle on Hob", description: "d", summary: "poll -> scene -> cond -> verdict" },
];

const passThrough = (name) => ({ name, template: "<div><slot /></div>" });
const stubs = {
  "v-card": passThrough("v-card"),
  "v-row": passThrough("v-row"),
  "v-col": passThrough("v-col"),
  "v-expansion-panels": passThrough("v-expansion-panels"),
  "v-expansion-panel": passThrough("v-expansion-panel"),
  "v-expansion-panel-title": passThrough("v-expansion-panel-title"),
  "v-expansion-panel-text": passThrough("v-expansion-panel-text"),
  "v-checkbox": {
    name: "v-checkbox",
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: `<input type="checkbox" :data-label="label" :checked="modelValue"
      @change="$emit('update:modelValue', $event.target.checked)" />`,
  },
  "v-select": {
    name: "v-select",
    props: ["modelValue", "label", "items"],
    emits: ["update:modelValue"],
    template: `<select :data-label="label" @change="$emit('update:modelValue', $event.target.value)">
      <option v-for="it in (items || [])" :key="it.value" :value="it.value">{{ it.title }}</option>
    </select>`,
  },
  "v-text-field": {
    name: "v-text-field",
    props: ["modelValue", "label", "placeholder"],
    emits: ["update:modelValue"],
    template: `<input :data-label="label" :data-placeholder="placeholder" :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)" />`,
  },
  "v-btn": { template: "<button><slot /></button>" },
  ZonePicker: { template: "<div class='zone-picker-stub' />" },
  GateEditorDialog: {
    name: "GateEditorDialog",
    props: ["modelValue", "gate"],
    template: "<div class='gate-editor-dialog-stub' :data-open='modelValue' />",
  },
};

function mountEditor(modelValue) {
  return mount(CompletionGateEditor, {
    props: {
      modelValue: { kinds: ["response", "vision_confirm"], vision: {}, ...modelValue },
    },
    global: { stubs, mocks: { $vuetify: { display: { smAndDown: false } } } },
  });
}

describe("CompletionGateEditor (VG08)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.api.getGatePresets.mockResolvedValue(PRESETS);
    mocks.api.createGateGraph.mockResolvedValue({ id: 99 });
  });

  it("has no dead 'Camera override' control (D25 regression)", async () => {
    const wrapper = mountEditor();
    await flushPromises();
    expect(wrapper.html()).not.toContain("Camera override");
  });

  it("loads the preset selector", async () => {
    const wrapper = mountEditor();
    await flushPromises();
    expect(mocks.api.getGatePresets).toHaveBeenCalled();
    const presetSelect = wrapper.find('[data-label="Vision gate preset"]');
    expect(presetSelect.exists()).toBe(true);
  });

  it("creates a gate graph from a chosen preset and stores its id", async () => {
    const wrapper = mountEditor();
    await flushPromises();
    const presetSelect = wrapper.find('[data-label="Vision gate preset"]');
    presetSelect.element.value = "kettle_on_hob";
    await presetSelect.trigger("change");
    await flushPromises();
    expect(mocks.api.createGateGraph).toHaveBeenCalledWith(
      expect.objectContaining({ from_preset: "kettle_on_hob" }),
    );
    const emitted = wrapper.emitted("update:modelValue").at(-1)[0];
    expect(emitted.vision.gate_graph_rule_id).toBe(99);
  });

  it("Watch is off by default and advanced fields show inherited placeholders", async () => {
    const wrapper = mountEditor();
    await flushPromises();
    const watchEnable = wrapper.find('[data-label="Enable background watch"]');
    expect(watchEnable.element.checked).toBe(false);
    // Inherit-as-placeholder: empty value, resolved default shown as placeholder.
    const window = wrapper.find('[data-label="Lookback window (s)"]');
    expect(window.attributes("data-placeholder")).toBe("20");
    expect(window.element.value).toBe("");
  });

  it("Edit vision logic opens the GateEditorDialog when a gate exists", async () => {
    const wrapper = mountEditor({ vision: { gate_graph_rule_id: 5 } });
    await flushPromises();
    const editBtn = wrapper.findAll("button").find((b) => b.text().includes("Edit vision logic"));
    await editBtn.trigger("click");
    const dialog = wrapper.findComponent({ name: "GateEditorDialog" });
    expect(dialog.props("modelValue")).toBe(true);
  });

  it("serialises sampling/cool-off edits to the new completion_gate.vision shape", async () => {
    const wrapper = mountEditor();
    await flushPromises();
    const maxFrames = wrapper.find('[data-label="Images (max frames)"]');
    maxFrames.element.value = "5";
    await maxFrames.trigger("input");
    const emitted = wrapper.emitted("update:modelValue").at(-1)[0];
    expect(emitted.vision.confirm.max_frames).toBe(5);
  });
});
