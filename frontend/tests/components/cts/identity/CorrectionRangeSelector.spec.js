import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";

vi.mock("@/services/timezone.js", () => ({ formatDateTime: (v) => v || "" }));
vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (u) => u }),
}));
vi.mock("@/components/common/CcSegmentedToggle.vue", () => ({
  default: {
    name: "CcSegmentedToggle",
    template: "<div class='toggle' />",
    props: ["modelValue", "options"],
  },
}));

import CorrectionRangeSelector from "@/components/cts/identity/CorrectionRangeSelector.vue";

const PROPOSAL = {
  ph_id: "ph-1",
  observation_ids: ["o1", "o2", "o3"],
  start: { observation_id: "o1", captured_at: "2026-06-20T12:00:00Z", reason: "split" },
  end: { observation_id: "o3", captured_at: "2026-06-20T12:00:10Z", reason: "segment_edge" },
  ph_version: 4,
};

const OBSERVATIONS = [
  {
    observation_id: "o1",
    captured_at: "2026-06-20T12:00:00Z",
    camera_id: "kitchen",
    image_url: "o1.jpg",
  },
  {
    observation_id: "o2",
    captured_at: "2026-06-20T12:00:05Z",
    camera_id: "kitchen",
    image_url: "o2.jpg",
  },
  {
    observation_id: "o3",
    captured_at: "2026-06-20T12:00:10Z",
    camera_id: "hall",
    image_url: "o3.jpg",
  },
];

const stubs = {
  "v-select": {
    name: "v-select",
    template:
      "<select :value='modelValue' @change=\"$emit('update:modelValue', $event.target.value)\"><option v-for='i in items' :key='i.value' :value='i.value'>{{ i.title }}</option></select>",
    props: ["modelValue", "items", "itemTitle", "itemValue"],
  },
  "v-img": { template: "<img :src='src' />", props: ["src"] },
  "v-icon": { template: "<i :data-icon='icon'><slot /></i>", props: ["icon"] },
  "v-tooltip": { template: "<span><slot /></span>" },
};

function mountSelector(props = {}) {
  return mount(CorrectionRangeSelector, {
    props: {
      proposal: PROPOSAL,
      observations: OBSERVATIONS,
      scopeMode: "segment",
      startId: "o1",
      endId: "o3",
      ...props,
    },
    global: { stubs },
  });
}

describe("CorrectionRangeSelector", () => {
  it("marks a hard boundary (split) with a lock and renders observation options", () => {
    const w = mountSelector();
    // start boundary reason is a hard 'split' -> lock icon present
    expect(w.find("[data-icon='mdi-lock']").exists()).toBe(true);
    // all proposed observations are selectable options
    expect(w.findAll("option").length).toBeGreaterThanOrEqual(3);
    expect(w.text()).toContain("3 observation(s) selected");
  });

  it("renders boundary thumbnails", () => {
    const w = mountSelector();
    const imgs = w.findAll("img");
    expect(imgs.length).toBe(2); // start + end thumbnails
    expect(imgs[0].attributes("src")).toBe("o1.jpg");
  });

  it("constrains the end options to not precede the start", () => {
    const w = mountSelector({ startId: "o2", endId: "o3" });
    const selects = w.findAllComponents({ name: "v-select" });
    // end select only offers o2, o3 (>= start index)
    const endItems = selects[1].props("items").map((i) => i.value);
    expect(endItems).toEqual(["o2", "o3"]);
  });

  it("shows the frame-only toggle only when allowed", () => {
    expect(mountSelector({ allowFrameOnly: false }).find(".toggle").exists()).toBe(false);
    expect(mountSelector({ allowFrameOnly: true }).find(".toggle").exists()).toBe(true);
  });

  it("describes frame-only scope when selected", () => {
    const w = mountSelector({ scopeMode: "frame_only", allowFrameOnly: true });
    expect(w.text()).toContain("single frame only");
  });
});
