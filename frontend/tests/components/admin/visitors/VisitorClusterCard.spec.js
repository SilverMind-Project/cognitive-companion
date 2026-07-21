import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";

vi.mock("@/services/timezone.js", () => ({
  formatDateOnly: (v) => `date:${v}`,
}));
vi.mock("@/composables/useFormatRelative.js", () => ({
  formatRelative: (v) => `relative:${v}`,
}));

import VisitorClusterCard from "@/components/admin/visitors/VisitorClusterCard.vue";

const stubs = {
  "v-card": { template: "<div><slot /></div>" },
  "v-chip": { template: "<span class='v-chip'><slot /></span>", props: ["color"] },
  "v-spacer": { template: "<span />" },
  "v-checkbox": {
    template:
      "<input type='checkbox' :checked='modelValue' @change=\"$emit('update:modelValue', $event.target.checked)\" />",
    props: ["modelValue"],
    emits: ["update:modelValue"],
  },
  "v-img": { template: "<img :src='src' />", props: ["src"] },
  "v-btn": {
    template: "<button :disabled='disabled' @click=\"$emit('click')\"><slot /></button>",
    props: ["disabled"],
    emits: ["click"],
  },
};

function baseCluster(overrides = {}) {
  return {
    cluster_id: "c1",
    status: "surfaced",
    sighting_count: 4,
    distinct_days: 3,
    first_seen_at: "2026-07-01T10:00:00Z",
    last_seen_at: "2026-07-19T10:00:00Z",
    recent_crop_urls: ["https://minio/a.jpg", "https://minio/b.jpg"],
    ...overrides,
  };
}

function mountCard(props) {
  return mount(VisitorClusterCard, { props, global: { stubs } });
}

describe("VisitorClusterCard", () => {
  it("renders crop thumbnails, counts, and dates", () => {
    const wrapper = mountCard({ cluster: baseCluster() });

    expect(wrapper.findAll("img")).toHaveLength(2);
    expect(wrapper.text()).toContain("4");
    expect(wrapper.text()).toContain("sightings");
    expect(wrapper.text()).toContain("3");
    expect(wrapper.text()).toContain("distinct days");
    expect(wrapper.text()).toContain("date:2026-07-01T10:00:00Z");
    expect(wrapper.text()).toContain("relative:2026-07-19T10:00:00Z");
  });

  it("shows a fallback message when there are no crops", () => {
    const wrapper = mountCard({ cluster: baseCluster({ recent_crop_urls: [] }) });

    expect(wrapper.findAll("img")).toHaveLength(0);
    expect(wrapper.text()).toContain("No crops available");
  });

  it("uses singular wording for one sighting on one day", () => {
    const wrapper = mountCard({ cluster: baseCluster({ sighting_count: 1, distinct_days: 1 }) });

    expect(wrapper.text()).toContain("1");
    expect(wrapper.text()).not.toContain("sightings");
    expect(wrapper.text()).not.toContain("distinct days");
  });

  it("emits name and dismiss with the right payloads", async () => {
    const wrapper = mountCard({ cluster: baseCluster() });

    await wrapper.findAll("button")[0].trigger("click");
    await wrapper.findAll("button")[1].trigger("click");

    expect(wrapper.emitted("name")[0]).toEqual([baseCluster()]);
    expect(wrapper.emitted("dismiss")[0]).toEqual(["c1"]);
  });

  it("disables Name and Dismiss once a cluster is named", () => {
    const wrapper = mountCard({ cluster: baseCluster({ status: "named" }) });

    const buttons = wrapper.findAll("button");
    expect(buttons[0].attributes("disabled")).toBeDefined();
    expect(buttons[1].attributes("disabled")).toBeDefined();
  });

  it("shows a checkbox and forwards toggle-select in merge mode", async () => {
    const wrapper = mountCard({ cluster: baseCluster(), mergeMode: true, selected: false });

    const checkbox = wrapper.find("input[type='checkbox']");
    expect(checkbox.exists()).toBe(true);
    await checkbox.setValue(true);

    expect(wrapper.emitted("toggle-select")[0]).toEqual(["c1"]);
  });

  it("hides the checkbox outside merge mode", () => {
    const wrapper = mountCard({ cluster: baseCluster(), mergeMode: false });

    expect(wrapper.find("input[type='checkbox']").exists()).toBe(false);
  });
});
