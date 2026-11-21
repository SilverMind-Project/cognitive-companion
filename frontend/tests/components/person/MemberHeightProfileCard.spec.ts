import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const notify = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify }),
}));

const personsApi = vi.hoisted(() => ({
  getPersonHeightProfile: vi.fn(),
  updatePerson: vi.fn(),
}));
vi.mock("@/services/modules/persons", () => personsApi);

import { ApiError } from "@/services/http";
import MemberHeightProfileCard from "@/components/person/MemberHeightProfileCard.vue";

const stubs = {
  "v-card": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-spacer": { template: "<span />" },
  "v-divider": { template: "<hr />" },
  "v-icon": { template: "<i><slot /></i>" },
  "v-chip": { template: "<span class='v-chip'><slot /></span>" },
  "v-alert": { template: "<div class='v-alert'><slot /><slot name='append' /></div>" },
  "v-progress-circular": { template: "<div />" },
  "v-text-field": {
    template:
      "<input :value='modelValue' @input=\"$emit('update:modelValue', $event.target.value)\" />",
    props: ["modelValue", "errorMessages"],
    emits: ["update:modelValue"],
  },
  "v-btn": {
    template: "<button :disabled='disabled' @click=\"$emit('click')\"><slot /></button>",
    props: ["disabled", "loading"],
    emits: ["click"],
  },
};

function mountCard(personId = "amma") {
  return mount(MemberHeightProfileCard, { props: { personId }, global: { stubs } });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("MemberHeightProfileCard", () => {
  it("renders a learned standing height profile with source chip and sample counts", async () => {
    personsApi.getPersonHeightProfile.mockResolvedValue({
      person_id: "amma",
      operator_height_cm: 155,
      effective_height_m: 1.54,
      effective_sigma_m: 0.032,
      source: "learned",
      samples: 280,
      cameras: 3,
      updated_at: "2026-11-21T10:00:00Z",
      cts_available: true,
    });

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.get("[data-test='height-source-chip']").text()).toBe("Learned");
    expect(wrapper.get("[data-test='height-effective']").text()).toContain("154.0 cm");
    expect(wrapper.get("[data-test='height-stats']").text()).toContain("280 standing samples");
    expect(wrapper.get("[data-test='height-stats']").text()).toContain("3 cameras");
  });

  it("renders empty state and saves a valid operator height", async () => {
    personsApi.getPersonHeightProfile
      .mockResolvedValueOnce({
        person_id: "amma",
        operator_height_cm: null,
        effective_height_m: null,
        effective_sigma_m: null,
        source: null,
        samples: 0,
        cameras: 0,
        updated_at: null,
        cts_available: true,
      })
      .mockResolvedValueOnce({
        person_id: "amma",
        operator_height_cm: 162,
        effective_height_m: 1.62,
        effective_sigma_m: 0.05,
        source: "operator",
        samples: 0,
        cameras: 0,
        updated_at: "2026-11-21T10:05:00Z",
        cts_available: true,
      });
    personsApi.updatePerson.mockResolvedValue({ id: "amma", height_cm: 162 });

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.find("[data-test='height-empty']").exists()).toBe(true);

    const input = wrapper.get("[data-test='height-input']");
    await input.setValue("162");
    await wrapper.get("[data-test='height-save']").trigger("click");
    await flushPromises();

    expect(personsApi.updatePerson).toHaveBeenCalledWith("amma", { height_cm: 162 });
    expect(notify.success).toHaveBeenCalled();
    expect(wrapper.get("[data-test='height-source-chip']").text()).toBe("Operator");
  });

  it("blocks out-of-range operator height values", async () => {
    personsApi.getPersonHeightProfile.mockResolvedValue({
      person_id: "amma",
      operator_height_cm: null,
      effective_height_m: null,
      effective_sigma_m: null,
      source: null,
      samples: 0,
      cameras: 0,
      updated_at: null,
      cts_available: true,
    });

    const wrapper = mountCard();
    await flushPromises();

    await wrapper.get("[data-test='height-input']").setValue("250");
    await flushPromises();

    expect(wrapper.get("[data-test='height-save']").attributes("disabled")).toBeDefined();
    expect(personsApi.updatePerson).not.toHaveBeenCalled();
  });

  it("shows CTS unreachable warning when cts_available is false", async () => {
    personsApi.getPersonHeightProfile.mockResolvedValue({
      person_id: "amma",
      operator_height_cm: 158,
      effective_height_m: null,
      effective_sigma_m: null,
      source: null,
      samples: 0,
      cameras: 0,
      updated_at: null,
      cts_available: false,
    });

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.find("[data-test='height-cts-unavailable']").exists()).toBe(true);
  });

  it("renders error alert on API failure", async () => {
    personsApi.getPersonHeightProfile.mockRejectedValue(new ApiError(500, "Server down"));

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.get("[data-test='height-error']").text()).toContain("Server down");
  });
});
