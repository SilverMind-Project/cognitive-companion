import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount, RouterLinkStub } from "@vue/test-utils";
import { computed, reactive } from "vue";

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn() } }),
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

const { store } = vi.hoisted(() => ({ store: { value: undefined as unknown } }));
vi.mock("@/composables/useFaceCalibrationReview", () => ({
  useFaceCalibrationReview: () => store.value,
}));

const { attestedAudit } = vi.hoisted(() => ({ attestedAudit: { value: undefined as unknown } }));
vi.mock("@/composables/useAttestedFaceAudit", () => ({
  useAttestedFaceAudit: () => attestedAudit.value,
}));

const { readinessSteps } = vi.hoisted(() => ({
  readinessSteps: { value: {} as Record<string, unknown> },
}));
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

vi.mock("@/services/modules/identity_targets", async () =>
  (await import("../support/reviewVocabulary")).identityTargetsModuleMock(),
);

import FaceCalibrationView from "@/views/admin/FaceCalibrationView.vue";

const stubs = {
  RouterLink: RouterLinkStub,
  "v-spacer": { template: "<span />" },
  "v-chip": { template: "<span class='v-chip'><slot /></span>", props: ["color"] },
  "v-alert": { template: "<div class='v-alert'><slot /><slot name='append' /></div>" },
  "v-btn": {
    template:
      "<button :disabled='disabled' :title='title' @click=\"$emit('click')\"><slot /></button>",
    props: ["disabled", "title"],
    emits: ["click"],
  },
  "v-progress-circular": { template: "<div />" },
  "v-progress-linear": { template: "<div />", props: ["modelValue"] },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-title": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-card-actions": { template: "<div><slot /></div>" },
  "v-dialog": { template: "<div v-if='modelValue'><slot /></div>", props: ["modelValue"] },
};

function mountView(options: { attachTo?: HTMLElement } = {}) {
  return mount(FaceCalibrationView, { ...options, global: { stubs } });
}

type Store = ReturnType<typeof makeStore>;
const current = () => store.value as Store;

function makeStore() {
  const state = reactive({
    queueState: "unlabeled" as "unlabeled" | "labeled",
    queue: [
      {
        candidate_id: "c1",
        captured_at: "2026-10-21T09:00:00Z",
        camera_id: "cam-1",
        crop_url: "https://minio/c1.png",
        quality_score: 0.41,
        interocular_px: 18,
        nearest_person_id: "amma",
        nearest_similarity: 0.36,
        pose_bin: "frontal",
        label_state: "unlabeled",
        label_kind: null as string | null,
        label_identity_id: null as string | null,
        promoted: false,
        promotion_eligible: false,
        promotion_ineligible_reason: null as string | null,
      },
    ],
    nextCursor: null,
    index: 0,
    residents: [{ identity_id: "amma", display_name: "Amma" }],
    summary: {
      identities: [
        { identity_id: "amma", labeled_faces: 30, episodes: 4, target_labeled_faces: 150 },
      ],
      not_enrolled_episodes: 2,
      capture_enabled: true,
    },
    loading: false,
    error: "",
    forbidden: false,
    acting: false,
    selecting: false,
    selection: [] as string[],
  });
  const actions = {
    load: vi.fn(),
    setQueueState: vi.fn(),
    labelResident: vi.fn(),
    labelNotEnrolled: vi.fn(),
    labelNotAFace: vi.fn(),
    reject: vi.fn(),
    remove: vi.fn(),
    promote: vi.fn(),
    next: vi.fn(),
    previous: vi.fn(),
    setSelecting: vi.fn((on: boolean) => {
      state.selecting = on;
    }),
    toggleSelection: vi.fn((id: string) => {
      state.selection = [...state.selection, id];
    }),
    selectAll: vi.fn(),
    clearSelection: vi.fn(),
    reviewSelected: vi.fn(),
  };
  return {
    state,
    current: computed(() => state.queue[state.index] ?? null),
    keyedResidents: computed(() => state.residents),
    actions,
  };
}

function press(key: string, target: EventTarget = window) {
  target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
}

function makeAttestedAudit() {
  const state = reactive({
    sample: [] as unknown[],
    index: 0,
    exemplars: [] as unknown[],
    summary: null,
    loading: false,
    error: "",
    forbidden: false,
    acting: false,
  });
  return {
    state,
    current: computed(() => null),
    actions: { load: vi.fn(), audit: vi.fn(), promote: vi.fn(), next: vi.fn(), previous: vi.fn() },
  };
}

beforeEach(() => {
  attestedAudit.value = makeAttestedAudit();
  store.value = makeStore();
  confirmResult.value = true;
  confirmResult.asked = [];
  readinessSteps.value = {};
});

function emptyAndCaptureOff() {
  const s = current();
  s.state.queue = [];
  s.state.summary = { ...s.state.summary, capture_enabled: false };
}

describe("FaceCalibrationView", () => {
  it("links to identity setup as step 3 of 8", () => {
    const wrapper = mountView();
    const link = wrapper.get("[data-test='setup-link']");
    expect(link.text()).toBe("Step 3 of 8 in identity setup");
    expect(wrapper.getComponent(RouterLinkStub).props("to")).toBe("/admin/identity-setup");
    wrapper.unmount();
  });

  it("names the next step in the empty queue when capture is off", async () => {
    emptyAndCaptureOff();
    readinessSteps.value = {
      capture: { key: "capture", state: "blocked", next_action: "enable_capture" },
    };
    const wrapper = mountView();
    await flushPromises();
    const next = wrapper.get("[data-test='capture-next']").text();
    expect(next).toContain("calibration_capture.enabled");
    expect(next).toContain("See identity setup");
    wrapper.unmount();
  });

  it("keeps the plain empty state while capture is on or readiness is unavailable", async () => {
    const s = current();
    s.state.queue = [];
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.find("[data-test='capture-next']").exists()).toBe(false);
    expect(wrapper.get("[data-test='empty-queue']").text()).toContain("switched on");
    wrapper.unmount();
  });

  it("loads on mount and shows the capture without a percentage", async () => {
    const wrapper = mountView({ attachTo: document.body });
    await flushPromises();
    expect(current().actions.load).toHaveBeenCalled();
    const text = wrapper.get("[data-test='current-capture']").text();
    expect(text).toContain("similarity 0.36");
    expect(text).not.toContain("%");
    expect(wrapper.get("[data-test='capture-chip']").text()).toContain("Capture on");
    wrapper.unmount();
  });

  it("labels from the keyboard: numbers for residents, n and x for the rest", async () => {
    const wrapper = mountView({ attachTo: document.body });
    await flushPromises();
    press("1");
    press("n");
    press("x");
    press("ArrowRight");
    press("ArrowLeft");
    expect(current().actions.labelResident).toHaveBeenCalledWith(0);
    expect(current().actions.labelNotEnrolled).toHaveBeenCalledTimes(1);
    expect(current().actions.labelNotAFace).toHaveBeenCalledTimes(1);
    expect(current().actions.next).toHaveBeenCalledTimes(1);
    expect(current().actions.previous).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("ignores keys typed into an input and stops listening after unmount", async () => {
    const wrapper = mountView({ attachTo: document.body });
    const input = document.createElement("input");
    document.body.appendChild(input);
    press("1", input);
    wrapper.unmount();
    press("n");
    expect(current().actions.labelResident).not.toHaveBeenCalled();
    expect(current().actions.labelNotEnrolled).not.toHaveBeenCalled();
    input.remove();
  });

  it("offers the shared decisions with the server's effects and guarantee", async () => {
    const wrapper = mountView({ attachTo: document.body });
    await flushPromises();
    const bar = wrapper.get("[data-test='verdict-bar']");
    expect(bar.get("[data-test='member-amma']").attributes("title")).toBe(
      "Server: labeled as Amma.",
    );
    expect(bar.get("[data-test='verdict-not_enrolled']").text()).toContain("Not in the household");
    expect(bar.get("[data-test='verdict-not_usable']").attributes("title")).toBe(
      "Server: left out of the fit.",
    );
    expect(bar.get("[data-test='verdict-guarantee']").text()).toBe(
      "Server: labels feed only the calibration fit.",
    );
    await bar.get("[data-test='verdict-not_usable']").trigger("click");
    expect(current().actions.labelNotAFace).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("labels several faces with a negative verdict only, after a confirm stating the effect", async () => {
    const wrapper = mountView({ attachTo: document.body });
    await flushPromises();
    await wrapper.get("[data-test='select-mode']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-test='current-capture']").exists()).toBe(false);
    await wrapper.get("[data-test='tile-c1']").trigger("click");

    // The vocabulary allows batch only for verdicts that name nobody.
    expect(wrapper.find("[data-test='batch-is_member']").exists()).toBe(false);
    await wrapper.get("[data-test='batch-not_enrolled']").trigger("click");
    await flushPromises();

    expect(confirmResult.asked[0]).toContain("Server: labeled as outside the household.");
    expect(current().actions.reviewSelected).toHaveBeenCalledWith("not_enrolled");
    // Keys do nothing while selecting.
    press("1");
    expect(current().actions.labelResident).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it("shows the empty state, not an empty grid, when selecting with nothing left", async () => {
    const s = current();
    s.state.selecting = true;
    s.state.queue = [];
    const wrapper = mountView();
    await flushPromises();
    expect(wrapper.find("[data-test='selection-grid']").exists()).toBe(false);
    expect(wrapper.find("[data-test='empty-queue']").exists()).toBe(true);
  });

  it("deletes only after confirmation", async () => {
    const wrapper = mountView({ attachTo: document.body });
    confirmResult.value = false;
    await wrapper.get("[data-test='delete']").trigger("click");
    await flushPromises();
    expect(current().actions.remove).not.toHaveBeenCalled();
    confirmResult.value = true;
    await wrapper.get("[data-test='delete']").trigger("click");
    await flushPromises();
    expect(current().actions.remove).toHaveBeenCalledTimes(1);
    wrapper.unmount();
  });

  it("shows an empty state when nothing is waiting", async () => {
    current().state.queue = [];
    const wrapper = mountView();
    expect(wrapper.find("[data-test='empty-queue']").exists()).toBe(true);
    wrapper.unmount();
  });

  it("shows the forbidden state instead of the queue", async () => {
    current().state.queue = [];
    current().state.forbidden = true;
    const wrapper = mountView();
    expect(wrapper.find("[data-test='forbidden']").exists()).toBe(true);
    expect(wrapper.find("[data-test='empty-queue']").exists()).toBe(false);
    expect(wrapper.find("[data-test='load-error']").exists()).toBe(false);
    wrapper.unmount();
  });

  it("shows promotion button with confirmation in labeled mode for eligible member captures", async () => {
    const s = current();
    s.state.queueState = "labeled";
    s.state.queue[0] = {
      ...s.state.queue[0],
      label_state: "labeled",
      label_kind: "member",
      label_identity_id: "amma",
      pose_bin: "down",
      promoted: false,
      promotion_eligible: true,
      promotion_ineligible_reason: null,
    };
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.get("[data-test='label-chip']").text()).toContain("Amma");
    const promoteBtn = wrapper.get("[data-test='promote']");
    expect(promoteBtn.attributes("disabled")).toBeUndefined();

    confirmResult.value = true;
    await promoteBtn.trigger("click");
    await flushPromises();

    expect(confirmResult.asked[0]).toContain("pause until the next calibration fit");
    expect(s.actions.promote).toHaveBeenCalledWith("c1");
    wrapper.unmount();
  });

  it("disables promotion and shows server reason when ineligible", async () => {
    const s = current();
    s.state.queueState = "labeled";
    s.state.queue[0] = {
      ...s.state.queue[0],
      label_state: "labeled",
      label_kind: "member",
      label_identity_id: "amma",
      promoted: false,
      promotion_eligible: false,
      promotion_ineligible_reason: "quality below 0.5",
    };
    const wrapper = mountView();
    await flushPromises();

    expect(wrapper.get("[data-test='promote']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-test='promotion-reason']").text()).toContain("quality below 0.5");
    wrapper.unmount();
  });
});

describe("FaceCalibrationView attested faces", () => {
  it("switches to the attested-face audit, loads it, and leaves the labeling queue alone", async () => {
    const wrapper = mountView();
    await flushPromises();
    const audit = attestedAudit.value as ReturnType<typeof makeAttestedAudit>;
    wrapper.findComponent({ name: "CcSegmentedToggle" }).vm.$emit("update:modelValue", "attested");
    await flushPromises();
    expect(audit.actions.load).toHaveBeenCalledTimes(1);
    expect(wrapper.find("[data-test=attested-faces]").exists()).toBe(true);
    expect(wrapper.find("[data-test=current-capture]").exists()).toBe(false);
    expect(current().actions.setQueueState).not.toHaveBeenCalled();
  });

  it("promotes an attested face only after a confirm that asks to check the person", async () => {
    const wrapper = mountView();
    await flushPromises();
    const audit = attestedAudit.value as ReturnType<typeof makeAttestedAudit>;
    wrapper.findComponent({ name: "CcSegmentedToggle" }).vm.$emit("update:modelValue", "attested");
    await flushPromises();
    wrapper.findComponent({ name: "AttestedFacesPanel" }).vm.$emit("promote", {
      candidate_id: "g1",
      label_identity_id: "amma",
      pose_bin: "left",
    });
    await flushPromises();
    expect(confirmResult.asked.at(-1)).toContain("Check that it really is");
    expect(audit.actions.promote).toHaveBeenCalledWith("g1");
  });
});
