import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import ImageSourceSelector, {
  DEFAULT_IMAGE_SOURCES,
} from "@/components/pipeline/steps/_shared/ImageSourceSelector.vue";

const stubs = {
  "v-select": {
    name: "VSelect",
    props: ["modelValue", "items"],
    emits: ["update:modelValue"],
    template: `<div class="v-select" :data-count="items.length" />`,
  },
  "v-text-field": {
    props: ["modelValue", "label", "hint"],
    template: `<div class="v-text-field" :data-label="label" :data-hint="hint" />`,
  },
  "v-card": { template: `<div class="v-card"><slot /></div>` },
  "v-checkbox": {
    props: ["modelValue", "label"],
    template: `<div class="v-checkbox" :data-label="label" />`,
  },
  CameraSelector: { name: "CameraSelector", template: `<div data-testid="camera-selector" />` },
  TimeFilterCard: { name: "TimeFilterCard", template: `<div data-testid="time-filter" />` },
};

function mountSelector(props = {}) {
  return mount(ImageSourceSelector, {
    props: { modelValue: { image_source: "trigger" }, ...props },
    global: { stubs },
  });
}

describe("ImageSourceSelector", () => {
  it("includes the unified media-window source", () => {
    const wrapper = mountSelector();
    expect(wrapper.find(".v-select").attributes("data-count")).toBe(
      String(DEFAULT_IMAGE_SOURCES.length),
    );
    expect(DEFAULT_IMAGE_SOURCES.some((source) => source.value === "media_window")).toBe(true);
  });

  it("honours a custom sources list (e.g. llm_call's None option)", () => {
    const sources = [{ title: "None", value: "none" }, ...DEFAULT_IMAGE_SOURCES];
    const wrapper = mountSelector({ sources });
    expect(wrapper.find(".v-select").attributes("data-count")).toBe(String(sources.length));
  });

  it("emits a patched config when the source changes", async () => {
    const wrapper = mountSelector({ modelValue: { image_source: "trigger", max_images: 3 } });
    wrapper.findComponent({ name: "VSelect" }).vm.$emit("update:modelValue", "additional");
    const events = wrapper.emitted("update:modelValue");
    expect(events).toHaveLength(1);
    expect(events[0][0]).toEqual({ image_source: "additional", max_images: 3 });
  });

  it("shows the reCamera selector only for additional/both sources", () => {
    expect(
      mountSelector({ modelValue: { image_source: "trigger" } })
        .find('[data-testid="camera-selector"]')
        .exists(),
    ).toBe(false);
    expect(
      mountSelector({ modelValue: { image_source: "additional" } })
        .find('[data-testid="camera-selector"]')
        .exists(),
    ).toBe(true);
    expect(
      mountSelector({ modelValue: { image_source: "both" } })
        .find('[data-testid="camera-selector"]')
        .exists(),
    ).toBe(true);
  });

  it("renders the time filter only when enabled and source is additional/both", () => {
    expect(
      mountSelector({ modelValue: { image_source: "additional" } })
        .find('[data-testid="time-filter"]')
        .exists(),
    ).toBe(false);
    expect(
      mountSelector({ modelValue: { image_source: "additional" }, showTimeFilter: true })
        .find('[data-testid="time-filter"]')
        .exists(),
    ).toBe(true);
    expect(
      mountSelector({ modelValue: { image_source: "trigger" }, showTimeFilter: true })
        .find('[data-testid="time-filter"]')
        .exists(),
    ).toBe(false);
  });

  it("hides max images for the none source even when enabled", () => {
    const withMax = mountSelector({ modelValue: { image_source: "trigger" }, showMaxImages: true });
    expect(
      withMax
        .findAll(".v-text-field")
        .some((f) => f.attributes("data-label") === "Max Images (total)"),
    ).toBe(true);
    const none = mountSelector({ modelValue: { image_source: "none" }, showMaxImages: true });
    expect(
      none
        .findAll(".v-text-field")
        .some((f) => f.attributes("data-label") === "Max Images (total)"),
    ).toBe(false);
  });

  it("shows the media-window output path field", () => {
    const wrapper = mountSelector({
      modelValue: {
        image_source: "media_window",
        pipeline_image_path: "steps.media.outputs",
      },
    });

    expect(
      wrapper
        .findAll(".v-text-field")
        .some((field) => field.attributes("data-label") === "Media Window Output Path"),
    ).toBe(true);
  });

  it("exposes isAdditional to the default slot", () => {
    const wrapper = mount(ImageSourceSelector, {
      props: { modelValue: { image_source: "both" } },
      global: { stubs },
      slots: {
        default: `<template #default="{ isAdditional }"><div class="slot-flag">{{ isAdditional }}</div></template>`,
      },
    });
    expect(wrapper.find(".slot-flag").text()).toBe("true");
  });
});
