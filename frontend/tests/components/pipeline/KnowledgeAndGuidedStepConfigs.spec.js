import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { chip, instanceOutputSchema, truncate } from "@/components/pipeline/steps/stepMeta.js";

vi.mock("@/services/modules/quizzes", () => ({
  getQuizzes: vi.fn(async () => ({
    items: [{ id: 3, title: "Family chat", question_count: 3, tags: ["family"] }],
    total: 1,
  })),
}));
vi.mock("@/services/modules/routines", () => ({
  listRoutines: vi.fn(async () => ({
    items: [
      { id: 7, name: "Morning tea", person_id: "vasanthi-amma", step_count: 4, is_enabled: true },
      { id: 8, name: "Old routine", person_id: "vasanthi-amma", step_count: 2, is_enabled: false },
    ],
    total: 2,
  })),
}));

const { getQuizzes } = await import("@/services/modules/quizzes");
const { listRoutines } = await import("@/services/modules/routines");
const KnowledgeQueryModule = await import("@/components/pipeline/steps/KnowledgeQueryConfig.vue");
const QuizStartModule = await import("@/components/pipeline/steps/QuizStartConfig.vue");
const GuidedModule = await import("@/components/pipeline/steps/GuidedTaskStartConfig.vue");

// Each stub renders a field addressable by its label and re-emits whatever the test types.
function field(name, extraProps = []) {
  return {
    name,
    props: ["modelValue", "label", "items", "disabled", ...extraProps],
    emits: ["update:modelValue"],
    template: `<div :data-field="label" :data-disabled="disabled"><slot /></div>`,
  };
}
const passthrough = { template: "<div><slot /></div>" };
const stubs = {
  TemplateInput: field("TemplateInput"),
  "v-text-field": field("v-text-field"),
  "v-combobox": field("v-combobox"),
  "v-switch": field("v-switch"),
  "v-checkbox": field("v-checkbox"),
  "v-select": field("v-select"),
  "v-autocomplete": field("v-autocomplete", ["loading"]),
  "v-alert": passthrough,
  "v-row": passthrough,
  "v-col": passthrough,
  "v-list-item": passthrough,
};

function mountConfig(module, modelValue = {}) {
  return mount(module.default, {
    props: { modelValue: { ...module.stepDefaults, ...modelValue } },
    global: { stubs },
  });
}

function byLabel(wrapper, label) {
  const found = Object.values(stubs)
    .filter((stub) => stub.name)
    .flatMap((stub) => wrapper.findAllComponents(stub))
    .find((c) => c.props("label") === label);
  if (!found) throw new Error(`no field labelled ${label}`);
  return found;
}

function lastEmit(wrapper) {
  const events = wrapper.emitted("update:modelValue");
  return events[events.length - 1][0];
}

afterEach(() => vi.clearAllMocks());

describe("KnowledgeQueryConfig", () => {
  it("emits the question, tags, and clamps overrides; blank inherits the household default", async () => {
    const wrapper = mountConfig(KnowledgeQueryModule);

    byLabel(wrapper, "Question").vm.$emit("update:modelValue", "What does {{person}} take?");
    expect(lastEmit(wrapper).query_text).toBe("What does {{person}} take?");

    byLabel(wrapper, "Only documents tagged (optional)").vm.$emit("update:modelValue", [
      "medication",
    ]);
    expect(lastEmit(wrapper).tags).toEqual(["medication"]);

    byLabel(wrapper, "Passages to retrieve").vm.$emit("update:modelValue", "50");
    expect(lastEmit(wrapper).top_k).toBe(20);

    byLabel(wrapper, "Passages to retrieve").vm.$emit("update:modelValue", "");
    expect(lastEmit(wrapper).top_k).toBeNull();

    byLabel(wrapper, "Minimum match strength (0 to 1)").vm.$emit("update:modelValue", "0.4");
    expect(lastEmit(wrapper).min_similarity).toBe(0.4);
  });

  it("defaults do not pin retrieval values (they follow the household settings)", () => {
    expect(KnowledgeQueryModule.stepDefaults).not.toHaveProperty("top_k");
    expect(KnowledgeQueryModule.stepDefaults).not.toHaveProperty("min_similarity");
  });

  it("chips summarize the question and tags", () => {
    const chips = KnowledgeQueryModule.chips(
      { query_text: "What medicine?", tags: ["medication"], log_interaction: true },
      { chip, truncate },
    );
    expect(chips.map((c) => c.label)).toEqual(["What medicine?", "tags: medication", "logged"]);
  });
});

describe("QuizStartConfig", () => {
  it("loads approved quizzes within the endpoint's limit and defaults to gentle mode", async () => {
    const wrapper = mountConfig(QuizStartModule);
    await flushPromises();

    expect(getQuizzes).toHaveBeenCalledWith({ status: "approved", limit: 200 });
    expect(byLabel(wrapper, "Quiz").props("items")).toHaveLength(1);
    expect(QuizStartModule.stepDefaults.interaction_mode).toBe("gentle");

    byLabel(wrapper, "Quiz").vm.$emit("update:modelValue", 3);
    expect(lastEmit(wrapper).quiz_id).toBe(3);
    byLabel(wrapper, "How answers are treated").vm.$emit("update:modelValue", "standard");
    expect(lastEmit(wrapper).interaction_mode).toBe("standard");
  });

  it("never lets both delivery channels be unchecked", async () => {
    const wrapper = mountConfig(QuizStartModule, { channels: ["pwa"] });

    byLabel(wrapper, "Companion tablet").vm.$emit("update:modelValue", false);

    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect(byLabel(wrapper, "Companion tablet").props("disabled")).toBe(true);
  });

  it("hides the voice instruction for a tablet-only quiz", () => {
    const wrapper = mountConfig(QuizStartModule, { channels: ["pwa"] });
    expect(() => byLabel(wrapper, "Voice instruction (optional)")).toThrow();
  });

  it("chips show the quiz, mode, and channels", () => {
    const chips = QuizStartModule.chips(
      { quiz_id: 3, interaction_mode: "gentle", channels: ["pwa", "voice"] },
      { chip },
    );
    expect(chips.map((c) => c.label)).toEqual(["Quiz #3", "gentle", "pwa + voice"]);
  });
});

describe("GuidedTaskStartConfig", () => {
  it("loads routines, emits the selection, and warns about a disabled routine", async () => {
    const wrapper = mountConfig(GuidedModule, { routine_id: 8 });
    await flushPromises();

    expect(listRoutines).toHaveBeenCalledWith({ limit: 200 });
    expect(wrapper.text()).toContain("This routine is disabled");

    byLabel(wrapper, "Routine").vm.$emit("update:modelValue", 7);
    expect(lastEmit(wrapper).routine_id).toBe(7);
  });

  it("clearing the summon timeout removes it so the configured default applies", () => {
    const wrapper = mountConfig(GuidedModule, { summon_timeout_s: 90 });

    byLabel(wrapper, "Give up waiting after (seconds)").vm.$emit("update:modelValue", "");

    expect(lastEmit(wrapper)).not.toHaveProperty("summon_timeout_s");
    expect(GuidedModule.stepDefaults).not.toHaveProperty("summon_timeout_s");
  });

  it("disables the summon timeout when the step starts immediately", () => {
    const wrapper = mountConfig(GuidedModule, { require_presence: false });
    expect(byLabel(wrapper, "Give up waiting after (seconds)").props("disabled")).toBe(true);
  });
});

describe("instanceOutputSchema", () => {
  const schema = {
    "x-output-key": { config_field: "output_key", default: "memory_context" },
    properties: { memory_context: { type: "object" } },
  };

  it("renames the default key to the step's configured output_key", () => {
    const out = instanceOutputSchema(schema, { output_key: "kitchen_memory" });
    expect(Object.keys(out.properties)).toEqual(["kitchen_memory"]);
  });

  it("keeps the default key when the step does not rename it", () => {
    expect(instanceOutputSchema(schema, {})).toBe(schema);
    expect(instanceOutputSchema(schema, { output_key: "memory_context" })).toBe(schema);
  });

  it("leaves schemas without the marker untouched", () => {
    const plain = { properties: { answer_text: { type: "string" } } };
    expect(instanceOutputSchema(plain, { output_key: "x" })).toBe(plain);
  });
});
