import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const notify = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify }),
}));

const confirmResult = vi.hoisted(() => ({ value: true, asked: [] as string[] }));
vi.mock("@/composables/useConfirm.js", async () => {
  const { ref } = await import("vue");
  return {
    useConfirm: () => ({
      confirmDialog: ref(false),
      confirmText: ref(""),
      confirmLabel: ref("Confirm"),
      cancelLabel: ref("Cancel"),
      confirmColor: ref("error"),
      require: (text: string) => {
        confirmResult.asked.push(text);
        return Promise.resolve(confirmResult.value);
      },
      onConfirm: vi.fn(),
      onCancel: vi.fn(),
    }),
  };
});

const protoApi = vi.hoisted(() => ({
  listPersonPrototypes: vi.fn(),
  rebuildPersonPrototypes: vi.fn(),
  deletePersonPrototype: vi.fn(),
}));
vi.mock("@/services/modules/face_calibration", () => protoApi);

import { ApiError } from "@/services/http";
import MemberPrototypesCard from "@/components/person/MemberPrototypesCard.vue";

const stubs = {
  "v-card": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-spacer": { template: "<span />" },
  "v-icon": { template: "<i><slot /></i>" },
  "v-chip": { template: "<span class='v-chip'><slot /></span>" },
  "v-alert": { template: "<div class='v-alert'><slot /><slot name='append' /></div>" },
  "v-progress-circular": { template: "<div />" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
  "v-btn": {
    template: "<button :disabled='disabled' @click=\"$emit('click')\"><slot /></button>",
    props: ["disabled"],
    emits: ["click"],
  },
};

function mountCard(personId = "amma") {
  return mount(MemberPrototypesCard, { props: { personId }, global: { stubs } });
}

beforeEach(() => {
  vi.clearAllMocks();
  confirmResult.value = true;
  confirmResult.asked = [];
});

describe("MemberPrototypesCard", () => {
  it("renders pose-binned prototypes with thumbnails and revision", async () => {
    protoApi.listPersonPrototypes.mockResolvedValue({
      person_id: "amma",
      gallery_revision: 3,
      counts_by_bin: { frontal: 1, down: 1 },
      prototypes: [
        {
          prototype_id: "p1",
          person_id: "amma",
          pose_bin: "frontal",
          member_count: 2,
          source: "enrollment",
          quality_score: 0.81,
          quality_version: "heuristic-v1",
          crop_url: null,
          approved_by: null,
          approved_at: null,
          created_at: "2026-11-19T08:00:00Z",
        },
        {
          prototype_id: "p2",
          person_id: "amma",
          pose_bin: "down",
          member_count: 1,
          source: "promoted_capture",
          quality_score: 0.72,
          quality_version: "heuristic-v1",
          crop_url: "https://minio/p2.png",
          approved_by: "caregiver-admin",
          approved_at: "2026-11-19T08:00:00Z",
          created_at: "2026-11-19T08:00:00Z",
        },
      ],
    });

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.get("[data-test='gallery-revision-chip']").text()).toContain("Revision 3");
    expect(wrapper.find("[data-test='pose-group-frontal']").exists()).toBe(true);
    expect(wrapper.find("[data-test='pose-group-down']").exists()).toBe(true);
    expect(wrapper.get("[data-test='prototype-p2'] img").attributes("src")).toBe(
      "https://minio/p2.png",
    );
    expect(wrapper.get("[data-test='prototype-p2']").text()).toContain("By caregiver-admin");
  });

  it("rebuilds prototypes and reloads", async () => {
    protoApi.listPersonPrototypes.mockResolvedValue({
      person_id: "amma",
      gallery_revision: 1,
      counts_by_bin: { frontal: 1 },
      prototypes: [
        {
          prototype_id: "p1",
          person_id: "amma",
          pose_bin: "frontal",
          member_count: 1,
          source: "enrollment",
          quality_score: null,
          quality_version: null,
          crop_url: null,
          approved_by: null,
          approved_at: null,
          created_at: null,
        },
      ],
    });
    protoApi.rebuildPersonPrototypes.mockResolvedValue({
      person_id: "amma",
      prototype_count: 2,
      counts_by_bin: { frontal: 2 },
    });

    const wrapper = mountCard();
    await flushPromises();
    await wrapper.get("[data-test='rebuild-prototypes']").trigger("click");
    await flushPromises();

    expect(protoApi.rebuildPersonPrototypes).toHaveBeenCalledWith("amma");
    expect(notify.success).toHaveBeenCalledWith("Rebuilt 2 prototype(s).");
    expect(protoApi.listPersonPrototypes).toHaveBeenCalledTimes(2);
  });

  it("requires confirmation before removing a prototype", async () => {
    protoApi.listPersonPrototypes.mockResolvedValue({
      person_id: "amma",
      gallery_revision: 2,
      counts_by_bin: { down: 1 },
      prototypes: [
        {
          prototype_id: "p2",
          person_id: "amma",
          pose_bin: "down",
          member_count: 1,
          source: "promoted_capture",
          quality_score: 0.72,
          quality_version: "heuristic-v1",
          crop_url: null,
          approved_by: "admin",
          approved_at: null,
          created_at: null,
        },
      ],
    });
    protoApi.deletePersonPrototype.mockResolvedValue(undefined);

    const wrapper = mountCard();
    await flushPromises();

    confirmResult.value = false;
    await wrapper.get("[data-test='delete-prototype-p2']").trigger("click");
    await flushPromises();
    expect(protoApi.deletePersonPrototype).not.toHaveBeenCalled();

    confirmResult.value = true;
    await wrapper.get("[data-test='delete-prototype-p2']").trigger("click");
    await flushPromises();
    expect(confirmResult.asked[0]).toContain("pause until the next calibration fit");
    expect(protoApi.deletePersonPrototype).toHaveBeenCalledWith("amma", "p2");
    expect(notify.success).toHaveBeenCalled();
  });

  it("shows empty, forbidden, and error states cleanly", async () => {
    protoApi.listPersonPrototypes.mockResolvedValueOnce({
      person_id: "amma",
      gallery_revision: 1,
      counts_by_bin: {},
      prototypes: [],
    });
    const emptyWrapper = mountCard();
    await flushPromises();
    expect(emptyWrapper.find("[data-test='prototypes-empty']").exists()).toBe(true);

    protoApi.listPersonPrototypes.mockRejectedValueOnce(new ApiError(403, "Forbidden"));
    const forbiddenWrapper = mountCard();
    await flushPromises();
    expect(forbiddenWrapper.find("[data-test='prototypes-forbidden']").exists()).toBe(true);

    protoApi.listPersonPrototypes.mockRejectedValueOnce(new Error("Upstream unavailable"));
    const errWrapper = mountCard();
    await flushPromises();
    expect(errWrapper.get("[data-test='prototypes-error']").text()).toContain(
      "Upstream unavailable",
    );
  });
});
