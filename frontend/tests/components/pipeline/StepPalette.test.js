import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  api: { getStepTypes: vi.fn() },
}));

vi.mock("@/services/api.js", () => ({ api: mocks.api }));

import StepPalette from "@/components/pipeline/StepPalette.vue";

const STEP_TYPES = [
  { type_name: "scene_analysis", display_name: "Scene Analysis", category: "perception", icon: "i", gate_safe: true, gate_only: false },
  { type_name: "notification", display_name: "Notification", category: "action", icon: "i", gate_safe: false, gate_only: false },
  { type_name: "gate_verdict", display_name: "Gate Verdict", category: "flow", icon: "i", gate_safe: true, gate_only: true },
];

// Render-through stubs so every step card (across all categories) is in the DOM.
const passThrough = (name) => ({ name, template: "<div><slot /></div>" });
const stubs = {
  "v-dialog": { props: ["modelValue"], template: "<div v-if='modelValue'><slot /></div>" },
  "v-card": passThrough("v-card"),
  "v-window": passThrough("v-window"),
  "v-window-item": passThrough("v-window-item"),
  "v-tabs": passThrough("v-tabs"),
  "v-tab": passThrough("v-tab"),
  "v-card-actions": passThrough("v-card-actions"),
  "v-divider": { template: "<hr />" },
  "v-icon": { template: "<i><slot /></i>" },
  "v-chip": passThrough("v-chip"),
  "v-spacer": { template: "<span />" },
  "v-btn": { template: "<button><slot /></button>" },
  "v-progress-circular": { template: "<div />" },
  DialogHeader: { template: "<div />" },
};

function labelsFor(wrapper) {
  return wrapper.findAll(".step-type-card").map((c) => c.text());
}

async function mountPalette(mode) {
  const wrapper = mount(StepPalette, {
    props: { modelValue: true, mode },
    global: { stubs, mocks: { $vuetify: { display: { smAndDown: false } } } },
  });
  await flushPromises();
  return wrapper;
}

describe("StepPalette mode filter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.api.getStepTypes.mockResolvedValue(STEP_TYPES);
  });

  it("gate mode shows only gate-safe steps and includes gate_verdict", async () => {
    const labels = labelsFor(await mountPalette("gate")).join(" ");
    expect(labels).toContain("Scene Analysis");
    expect(labels).toContain("Gate Verdict");
    expect(labels).not.toContain("Notification");
  });

  it("rule mode shows normal steps but hides gate_only (gate_verdict)", async () => {
    const labels = labelsFor(await mountPalette("rule")).join(" ");
    expect(labels).toContain("Scene Analysis");
    expect(labels).toContain("Notification");
    expect(labels).not.toContain("Gate Verdict");
  });
});
