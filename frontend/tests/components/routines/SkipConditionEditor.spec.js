import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const mocks = vi.hoisted(() => ({
  api: { getActivityTypeOptions: vi.fn() },
}));
vi.mock("@/services/api.js", () => ({ api: mocks.api }));

import SkipConditionEditor from "@/components/routines/SkipConditionEditor.vue";
import { resetActivityTypeOptions } from "@/composables/useActivityTypeOptions.js";

const stubs = {
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-select": {
    props: ["modelValue", "items", "label"],
    emits: ["update:modelValue"],
    template: `<select :data-label="label" @change="$emit('update:modelValue', $event.target.value)">
      <option v-for="it in (items || [])" :key="it.value" :value="it.value">{{ it.title }}</option>
    </select>`,
  },
  "v-text-field": {
    props: ["modelValue", "label"],
    emits: ["update:modelValue"],
    template: `<input :data-label="label" :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)" />`,
  },
  ZonePicker: {
    props: ["modelValue", "roomId", "label"],
    emits: ["update:modelValue"],
    template: "<button class='zone-picker-stub' @click=\"$emit('update:modelValue', 3)\" />",
  },
};

function mountEditor(modelValue = null) {
  return mount(SkipConditionEditor, {
    props: { modelValue, roomId: 1 },
    global: { stubs },
  });
}

const lastEmit = (wrapper) => wrapper.emitted("update:modelValue").at(-1)[0];

describe("SkipConditionEditor", () => {
  beforeEach(() => {
    resetActivityTypeOptions();
    mocks.api.getActivityTypeOptions.mockResolvedValue({
      activity_types: ["cooking", "medication"],
    });
  });

  it("emits only the shapes the backend evaluates", async () => {
    const wrapper = mountEditor();
    const kind = wrapper.find("[data-test=skip-kind]");

    await kind.setValue("response_says_done");
    expect(lastEmit(wrapper)).toEqual({ kind: "response_says_done" });

    await kind.setValue("zone_presence");
    expect(lastEmit(wrapper)).toEqual({ kind: "zone_presence", zone_id: null });

    await kind.setValue("none");
    expect(lastEmit(wrapper)).toBeNull();
  });

  it("builds an activity condition from the backend's activity types", async () => {
    const wrapper = mountEditor({ kind: "activity_signal" });
    await flushPromises();

    const select = wrapper.find("[data-test=activity-type]");
    expect(select.findAll("option").map((o) => o.element.value)).toEqual(["cooking", "medication"]);
    await select.setValue("cooking");
    expect(lastEmit(wrapper)).toEqual({ kind: "activity_signal", activity_type: "cooking" });

    await wrapper.setProps({ modelValue: lastEmit(wrapper) });
    await wrapper.find("[data-test=activity-window]").setValue("5");
    expect(lastEmit(wrapper)).toEqual({
      kind: "activity_signal",
      activity_type: "cooking",
      window_minutes: 5,
    });
  });

  it("targets a zone, or the step's own zone when left empty", async () => {
    const wrapper = mountEditor({ kind: "zone_presence", zone_id: null });

    await wrapper.find(".zone-picker-stub").trigger("click");

    expect(lastEmit(wrapper)).toEqual({ kind: "zone_presence", zone_id: 3 });
  });
});
