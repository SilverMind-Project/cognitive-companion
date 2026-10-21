import { describe, it, expect, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
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

import FaceCalibrationView from "@/views/admin/FaceCalibrationView.vue";

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
    residents: [{ id: "amma", name: "Amma" }],
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
});

describe("FaceCalibrationView", () => {
  it("loads on mount and shows the capture without a percentage", async () => {
    const wrapper = mount(FaceCalibrationView, { attachTo: document.body });
    await flushPromises();
    expect(current().actions.load).toHaveBeenCalled();
    const text = wrapper.get("[data-test='current-capture']").text();
    expect(text).toContain("similarity 0.36");
    expect(text).not.toContain("%");
    expect(wrapper.get("[data-test='capture-chip']").text()).toContain("Capture on");
    wrapper.unmount();
  });

  it("labels from the keyboard: numbers for residents, n and x for the rest", async () => {
    const wrapper = mount(FaceCalibrationView, { attachTo: document.body });
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
    const wrapper = mount(FaceCalibrationView, { attachTo: document.body });
    const input = document.createElement("input");
    document.body.appendChild(input);
    press("1", input);
    wrapper.unmount();
    press("n");
    expect(current().actions.labelResident).not.toHaveBeenCalled();
    expect(current().actions.labelNotEnrolled).not.toHaveBeenCalled();
    input.remove();
  });

  it("deletes only after confirmation", async () => {
    const wrapper = mount(FaceCalibrationView, { attachTo: document.body });
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
    const wrapper = mount(FaceCalibrationView);
    expect(wrapper.find("[data-test='empty-queue']").exists()).toBe(true);
    wrapper.unmount();
  });

  it("shows the forbidden state instead of the queue", async () => {
    current().state.queue = [];
    current().state.forbidden = true;
    const wrapper = mount(FaceCalibrationView);
    expect(wrapper.find("[data-test='forbidden']").exists()).toBe(true);
    expect(wrapper.find("[data-test='empty-queue']").exists()).toBe(false);
    expect(wrapper.find("[data-test='load-error']").exists()).toBe(false);
    wrapper.unmount();
  });
});
