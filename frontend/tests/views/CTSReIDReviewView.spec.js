import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref, computed } from "vue";

vi.mock("@/composables/useNotify", () => ({
  useNotify: () => ({
    snack: ref(false),
    snackText: ref(""),
    snackColor: ref("success"),
    notify: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
  }),
}));
vi.mock("@/composables/useBlurMode", () => ({
  useBlurMode: () => ({ blurMode: ref(true) }),
  useDisplaySrc: () => ({ displaySrc: (u) => u }),
}));
vi.mock("@/services/timezone", () => ({
  formatDateTime: (v) => v || "-",
  formatDateTimeShort: (v) => v || "",
}));
vi.mock("@/services/cts_ph", () => ({
  ctsPh: { observations: vi.fn().mockResolvedValue({ observations: [] }) },
}));
vi.mock("@/components/cts/BlurToggle.vue", () => ({
  default: { template: "<div class='blur-toggle' />" },
}));
vi.mock("@/components/cts/identity/IdentityBboxOverlay.vue", () => ({
  default: {
    name: "IdentityBboxOverlay",
    props: ["imageUrl", "bboxes", "selectable"],
    template: "<div class='ov' />",
  },
}));

const { store } = vi.hoisted(() => ({ store: {} }));

vi.mock("@/composables/useReIDReview", () => ({
  useReIDReview: () => store.value,
}));
vi.mock("@/services/cts_identity", () => {
  class CorrectionError extends Error {
    constructor(m, { status = 0 } = {}) {
      super(m);
      this.status = status;
    }
  }
  return { CorrectionError };
});

import CTSReIDReviewView from "@/views/admin/CTSReIDReviewView.vue";

function makeStore(overrides = {}) {
  const candidates = ref(overrides.candidates || []);
  const detail = ref(overrides.detail || null);
  return {
    state: {
      candidates,
      total: ref(candidates.value.length),
      limit: ref(25),
      offset: ref(0),
      page: computed(() => 1),
      pageCount: computed(() => 1),
      listLoading: ref(false),
      listError: ref(""),
      filters: ref({
        state: "pending_review",
        identity_id: null,
        camera_id: null,
        model_version: null,
        source_type: null,
      }),
      selected: ref(new Set()),
      selectedIds: computed(() => []),
      detail,
      detailLoading: ref(false),
      detailError: ref(""),
      acting: ref(false),
      counts: ref({ pending_review: 4, operator_verified: 2, rejected: 1 }),
      targets: ref([{ identity_id: "amma", display_name: "Amma" }]),
      targetsLoading: ref(false),
    },
    actions: {
      loadList: vi.fn(),
      loadCounts: vi.fn(),
      loadTargets: vi.fn(),
      invalidate: vi.fn().mockResolvedValue(),
      setFilter: vi.fn(),
      goToPage: vi.fn(),
      openDetail: vi.fn(),
      closeDetail: vi.fn(),
      toggleSelected: vi.fn(),
      clearSelection: vi.fn(),
      approve: vi.fn(),
      relabel: vi.fn(),
      reject: vi.fn(),
      rejectSelected: vi.fn(),
      compensate: vi.fn(),
    },
  };
}

const stubs = {
  "v-chip": { template: "<span class='v-chip'><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-btn": { template: "<button :disabled='disabled'><slot /></button>", props: ["disabled"] },
  "v-alert": { template: "<div class='v-alert'><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-select": { template: "<select />", props: ["modelValue", "items"] },
  "v-autocomplete": {
    template: "<select class='target-select' />",
    props: ["modelValue", "items", "loading"],
  },
  "v-text-field": { template: "<input />", props: ["modelValue"] },
  "v-textarea": { template: "<textarea />", props: ["modelValue"] },
  "v-table": { template: "<table><slot /></table>" },
  "v-checkbox": {
    template: "<input type='checkbox' :disabled='disabled' />",
    props: ["modelValue", "disabled"],
  },
  "v-progress-circular": { template: "<div />" },
  "v-pagination": { template: "<div class='pager' />", props: ["modelValue", "length"] },
  "v-navigation-drawer": {
    template: "<div v-if='modelValue'><slot /></div>",
    props: ["modelValue"],
  },
  "v-divider": { template: "<hr />" },
  "v-timeline": { template: "<div><slot /></div>" },
  "v-timeline-item": { template: "<div><slot /></div>" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-snackbar": { template: "<div><slot /></div>", props: ["modelValue"] },
  "v-slide-y-transition": { template: "<div><slot /></div>" },
  "v-expand-transition": { template: "<div><slot /></div>" },
  "v-icon": { template: "<span />" },
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CTSReIDReviewView", () => {
  it("renders queue counts and an empty state", async () => {
    store.value = makeStore({ candidates: [] });
    const wrapper = mount(CTSReIDReviewView, { global: { stubs } });
    await flushPromises();
    expect(wrapper.text()).toContain("4 pending");
    expect(wrapper.text()).toContain("No candidates match");
  });

  it("has no bulk-approve control (batch is reject-only)", async () => {
    store.value = makeStore({
      candidates: [{ candidate_id: "c1", state: "pending_review", audit_version: 1 }],
    });
    const wrapper = mount(CTSReIDReviewView, { global: { stubs } });
    await flushPromises();
    expect(wrapper.text().toLowerCase()).not.toContain("approve selected");
  });

  it("disables Approve when server eligibility is false", async () => {
    store.value = makeStore({
      detail: {
        candidate: {
          candidate_id: "c1",
          state: "pending_review",
          audit_version: 1,
          model_version: "v0",
        },
        events: [],
        eligibility: {
          eligible: false,
          model_compatible: false,
          reasons: ["incompatible_model:v0"],
        },
      },
    });
    const wrapper = mount(CTSReIDReviewView, { global: { stubs } });
    await flushPromises();
    const approveBtn = wrapper.findAll("button").find((b) => b.text() === "Approve");
    expect(approveBtn).toBeTruthy();
    expect(approveBtn.attributes("disabled")).toBeDefined();
  });

  it("shows a deleted-crop state for a rejected candidate without a broken image", async () => {
    store.value = makeStore({
      detail: {
        candidate: { candidate_id: "c1", state: "rejected", audit_version: 2, crop_url: null },
        events: [
          {
            event_id: "e1",
            previous_state: "pending_review",
            new_state: "rejected",
            actor: "a",
            event_time: "t",
            audit_version: 2,
          },
        ],
        eligibility: { eligible: false, model_compatible: true, reasons: [] },
      },
    });
    const wrapper = mount(CTSReIDReviewView, { global: { stubs } });
    await flushPromises();
    expect(wrapper.text()).toContain("Crop deleted");
    expect(wrapper.find("img.crop-img").exists()).toBe(false);
  });

  it("renders a forbidden message when the queue load is forbidden", async () => {
    const s = makeStore();
    const { CorrectionError } = await import("@/services/cts_identity");
    s.actions.invalidate = vi
      .fn()
      .mockRejectedValue(new CorrectionError("forbidden", { status: 403 }));
    store.value = s;
    const wrapper = mount(CTSReIDReviewView, { global: { stubs } });
    await flushPromises();
    expect(wrapper.text()).toContain("cts.identity.gallery_review");
  });
});
