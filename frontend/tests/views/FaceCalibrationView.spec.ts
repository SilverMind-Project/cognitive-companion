import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount, RouterLinkStub } from "@vue/test-utils";
import { computed, reactive } from "vue";

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn() } }),
}));

const confirmResult = vi.hoisted(() => ({ value: true }));
vi.mock("@/composables/useConfirm.js", async () => {
  const { ref } = await import("vue");
  return {
    useConfirm: () => ({
      confirmDialog: ref(false),
      confirmTitle: ref(""),
      confirmText: ref(""),
      showConfirm: () => Promise.resolve(confirmResult.value),
      onConfirm: vi.fn(),
      onCancel: vi.fn(),
    }),
  };
});

const { store } = vi.hoisted(() => ({ store: { value: undefined as unknown } }));
vi.mock("@/composables/useFaceCalibrationReview", () => ({
  useFaceCalibrationReview: () => store.value,
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
    template: "<button :disabled='disabled' :title='title'><slot /></button>",
    props: ["disabled", "title"],
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
  });
  const actions = {
    load: vi.fn(),
    labelResident: vi.fn(),
    labelNotEnrolled: vi.fn(),
    labelNotAFace: vi.fn(),
    reject: vi.fn(),
    remove: vi.fn(),
    next: vi.fn(),
    previous: vi.fn(),
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

beforeEach(() => {
  store.value = makeStore();
  confirmResult.value = true;
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
});
