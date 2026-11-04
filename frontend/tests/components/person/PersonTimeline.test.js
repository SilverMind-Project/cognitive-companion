import { describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const getTimeline = vi.hoisted(() => vi.fn());
vi.mock("@/services/api.js", () => ({ api: { getTimeline } }));

import PersonTimeline from "@/components/person/PersonTimeline.vue";

const slot = { template: "<div><slot /></div>" };

describe("PersonTimeline", () => {
  it("loads the person's timeline", async () => {
    getTimeline.mockResolvedValue([]);
    const wrapper = mount(PersonTimeline, {
      props: { personId: "rose" },
      global: {
        stubs: {
          "v-alert": slot,
          "v-btn": slot,
          "v-card": slot,
          "v-card-text": slot,
          "v-card-title": slot,
          "v-chip": slot,
          "v-icon": slot,
          "v-progress-linear": slot,
          "v-spacer": slot,
          "v-timeline": slot,
          "v-timeline-item": slot,
        },
      },
    });
    await wrapper.vm.load();
    await flushPromises();
    expect(getTimeline).toHaveBeenCalledWith("rose", expect.objectContaining({ hours: 24 }));
  });
});
