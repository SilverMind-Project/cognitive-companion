import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import LearnedTransitionsCard from "@/components/cts/LearnedTransitionsCard.vue";

const getLearnedTransitions = vi.fn();

vi.mock("@/services/cts.js", () => ({
  cts: { getLearnedTransitions: (...args) => getLearnedTransitions(...args) },
}));

const stubs = {
  "v-card": { template: "<section><slot /></section>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-subtitle": { template: "<div><slot /></div>" },
  "v-divider": { template: "<hr />" },
  "v-table": { template: "<table><slot /></table>" },
};

function mountCard() {
  return mount(LearnedTransitionsCard, {
    props: { cameraNames: { "cam-a": "Corridor", "cam-b": "Kitchen" } },
    global: { stubs },
  });
}

describe("LearnedTransitionsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("shows each handoff pair by name with its count and delay after close", async () => {
    getLearnedTransitions.mockResolvedValue({
      transitions: [
        {
          from_camera: "cam-a",
          to_camera: "cam-b",
          observation_count: 2,
          mean_transit_s: 6.25,
          std_transit_s: 1.0,
          last_updated_at: null,
        },
      ],
    });
    const wrapper = mountCard();
    await flushPromises();

    const row = wrapper.find("[data-testid='transition-cam-a-cam-b']");
    expect(row.text()).toContain("Corridor");
    expect(row.text()).toContain("Kitchen");
    expect(row.text()).toContain("6.3 s");
    expect(row.findAll("td")[2].text()).toBe("2");
  });

  it("explains when there are no handoffs yet", async () => {
    getLearnedTransitions.mockResolvedValue({ transitions: [] });
    const wrapper = mountCard();
    await flushPromises();
    expect(wrapper.text()).toContain("No handoffs yet");
  });

  it("says when tracking cannot be reached", async () => {
    getLearnedTransitions.mockRejectedValue(new Error("down"));
    const wrapper = mountCard();
    await flushPromises();
    expect(wrapper.text()).toContain("Tracking is not reachable");
  });
});
