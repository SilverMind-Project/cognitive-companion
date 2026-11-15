import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises, RouterLinkStub } from "@vue/test-utils";
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

const { store, readinessSteps } = vi.hoisted(() => ({ store: {}, readinessSteps: { value: {} } }));

vi.mock("@/composables/useIdentityReadiness", async () => {
  const { computed } = await import("vue");
  return {
    useIdentityReadiness: () => ({
      state: {},
      stepByKey: computed(() => readinessSteps.value),
      actions: { load: vi.fn() },
    }),
  };
});

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

vi.mock("@/services/modules/identity_targets", async () =>
  (await import("../support/reviewVocabulary")).identityTargetsModuleMock(),
);

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
      counts: ref({ pending_review: 4, auto_verified: 3, operator_verified: 2, rejected: 1 }),
      countsLoaded: ref(true),
      countsError: ref(""),
      targets: ref([
        { identity_id: "amma", display_name: "Amma" },
        { identity_id: "appa", display_name: "Appa" },
      ]),
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
      approve: vi.fn().mockResolvedValue(),
      relabel: vi.fn().mockResolvedValue(),
      demote: vi.fn().mockResolvedValue(),
      reject: vi.fn().mockResolvedValue(),
      rejectSelected: vi.fn().mockResolvedValue(),
      compensate: vi.fn().mockResolvedValue(),
    },
  };
}

const stubs = {
  "v-chip": { template: "<span class='v-chip'><slot /></span>" },
  "v-spacer": { template: "<span />" },
  "v-btn": {
    template: "<button :disabled='disabled' :title='title'><slot /></button>",
    props: ["disabled", "title"],
  },
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

function mountView() {
  return mount(CTSReIDReviewView, {
    global: {
      stubs: { ...stubs, RouterLink: RouterLinkStub },
      mocks: { $vuetify: { display: { smAndDown: false } } },
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  readinessSteps.value = {};
});

function detailOf(candidate = {}, eligibility = null) {
  return {
    candidate: {
      candidate_id: "c1",
      state: "pending_review",
      audit_version: 1,
      model_version: "v1",
      ...candidate,
    },
    events: [],
    eligibility: eligibility ?? { eligible: true, model_compatible: true, reasons: [] },
  };
}

function confirmButton(wrapper) {
  return wrapper.findAll("button").find((b) => b.text() === "Confirm");
}

function emptyQueueStore() {
  const s = makeStore({ candidates: [] });
  s.state.counts.value = { pending_review: 0, auto_verified: 0, operator_verified: 0, rejected: 0 };
  return s;
}

describe("CTSReIDReviewView", () => {
  it("uses the standard admin page title", async () => {
    store.value = makeStore({ candidates: [] });
    const wrapper = mountView();
    await flushPromises();
    const title = wrapper.find("h2");
    expect(title.text()).toBe("ReID Review Queue");
    expect(title.classes()).toEqual(
      expect.arrayContaining(["text-h4", "font-weight-bold", "tracking-tight"]),
    );
    expect(wrapper.find("h1").exists()).toBe(false);
  });

  it("renders queue counts in the state picker and a filter-miss empty state", async () => {
    store.value = makeStore({ candidates: [] });
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("Pending · 4");
    expect(wrapper.text()).toContain("Auto-verified · 3");
    expect(wrapper.text()).toContain("No candidates match");
    expect(wrapper.text()).not.toContain("The review queue is empty");
  });

  it("explains how candidates arrive when the queue has never had one", async () => {
    const s = makeStore({ candidates: [] });
    s.state.counts.value = {
      pending_review: 0,
      auto_verified: 0,
      operator_verified: 0,
      rejected: 0,
    };
    store.value = s;
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("The review queue is empty");
    expect(wrapper.text()).toContain("calibrated face match");
    expect(wrapper.text()).not.toContain("No candidates match");
  });

  it("says no samples can be proposed while calibrated faces are not live", async () => {
    readinessSteps.value = {
      artifact: { key: "artifact", state: "blocked" },
      face_policy: { key: "face_policy", state: "attention" },
    };
    store.value = emptyQueueStore();
    const wrapper = mountView();
    await flushPromises();
    const hint = wrapper.get("[data-test='not-proposable']");
    expect(hint.text()).toContain("no samples can be proposed");
    expect(hint.text()).toContain("See identity setup");
  });

  it("drops the readiness hint once calibrated faces are live", async () => {
    readinessSteps.value = {
      artifact: { key: "artifact", state: "ready" },
      face_policy: { key: "face_policy", state: "ready" },
    };
    store.value = emptyQueueStore();
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("The review queue is empty");
    expect(wrapper.find("[data-test='not-proposable']").exists()).toBe(false);
  });

  it("shows no readiness hint when readiness could not be read", async () => {
    store.value = emptyQueueStore();
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.find("[data-test='not-proposable']").exists()).toBe(false);
  });

  it("switches lifecycle state through the segmented picker", async () => {
    store.value = makeStore({ candidates: [] });
    const wrapper = mountView();
    await flushPromises();
    const rejected = wrapper.findAll("button").find((b) => b.text() === "Rejected · 1");
    await rejected.trigger("click");
    expect(store.value.actions.setFilter).toHaveBeenCalledWith("state", "rejected");
  });

  it("renders a distinct auto_verified state chip in the queue table", async () => {
    store.value = makeStore({
      candidates: [{ candidate_id: "c1", state: "auto_verified", audit_version: 1, quality: 0.9 }],
    });
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("Auto-verified");
  });

  it("offers the shared decisions plus Demote for an auto_verified candidate", async () => {
    store.value = makeStore({ detail: detailOf({ state: "auto_verified" }) });
    const wrapper = mountView();
    await flushPromises();
    const bar = wrapper.get("[data-test='verdict-bar']");
    expect(bar.get("[data-test='demote']").text()).toBe("Demote");
    expect(bar.get("[data-test='member-amma']").attributes("disabled")).toBeUndefined();
    expect(bar.get("[data-test='member-amma']").attributes("title")).toBe(
      "Server: verified as Amma.",
    );
    expect(bar.get("[data-test='verdict-not_enrolled']").text()).toContain("Not in the household");
    expect(bar.get("[data-test='verdict-guarantee']").text()).toBe(
      "Server: body samples never change face enrollment.",
    );
  });

  it("approves the proposal and relabels anyone else, each only after a confirm", async () => {
    store.value = makeStore({ detail: detailOf({ proposed_identity_id: "amma" }) });
    const wrapper = mountView();
    await flushPromises();

    await wrapper.get("[data-test='member-amma']").trigger("click");
    await flushPromises();
    expect(store.value.actions.approve).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Server: verified as Amma.");
    await confirmButton(wrapper).trigger("click");
    await flushPromises();
    expect(store.value.actions.approve).toHaveBeenCalledWith("c1");

    await wrapper.get("[data-test='member-appa']").trigger("click");
    await flushPromises();
    await confirmButton(wrapper).trigger("click");
    await flushPromises();
    expect(store.value.actions.relabel).toHaveBeenCalledWith("c1", { target_identity_id: "appa" });
  });

  it("a member key opens the confirm instead of approving", async () => {
    store.value = makeStore({ detail: detailOf({ proposed_identity_id: "amma" }) });
    const wrapper = mountView();
    await flushPromises();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "1" }));
    await flushPromises();
    expect(store.value.actions.approve).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("Verify as Amma");
    wrapper.unmount();
  });

  it("not in the household rejects as the wrong person after a confirm", async () => {
    store.value = makeStore({ detail: detailOf() });
    const wrapper = mountView();
    await flushPromises();
    await wrapper.get("[data-test='verdict-not_enrolled']").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Server: rejected as the wrong person.");
    await confirmButton(wrapper).trigger("click");
    await flushPromises();
    expect(store.value.actions.reject).toHaveBeenCalledWith("c1", { reason: "wrong_person" });
  });

  it("has no bulk-approve control (batch is reject-only)", async () => {
    store.value = makeStore({
      candidates: [{ candidate_id: "c1", state: "pending_review", audit_version: 1 }],
    });
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text().toLowerCase()).not.toContain("approve selected");
  });

  it("disables member decisions, and says why, when server eligibility is false", async () => {
    store.value = makeStore({
      detail: detailOf(
        { model_version: "v0" },
        { eligible: false, model_compatible: false, reasons: ["incompatible_model:v0"] },
      ),
    });
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.get("[data-test='member-amma']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-test='members-disabled-reason']").text()).toContain(
      "incompatible_model:v0",
    );
    // A rejection stays possible.
    expect(wrapper.get("[data-test='verdict-not_usable']").attributes("disabled")).toBeUndefined();
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
    const wrapper = mountView();
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
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.text()).toContain("cts.identity.gallery_review");
  });

  it("does not claim an empty queue when the counts failed to load", async () => {
    const s = makeStore({ candidates: [] });
    s.state.counts.value = {
      pending_review: 0,
      auto_verified: 0,
      operator_verified: 0,
      rejected: 0,
    };
    s.state.countsError.value = "tracking_orchestrator returned HTTP 503";
    store.value = s;
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.text()).toContain("Counts unavailable");
    expect(wrapper.text()).not.toContain("The review queue is empty");
    expect(wrapper.text()).not.toContain("Pending · 0");
    expect(wrapper.text()).toContain("No candidates match");
  });
});
