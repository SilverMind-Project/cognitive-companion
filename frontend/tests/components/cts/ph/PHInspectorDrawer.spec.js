import { mount } from "@vue/test-utils";
import { describe, it, expect, vi } from "vitest";
import PHInspectorDrawer from "@/components/cts/ph/PHInspectorDrawer.vue";

// Mock composables
vi.mock("@/composables/usePHDetail", () => ({
  usePHDetail: () => ({
    state: {
      detail: {
        value: {
          ph_id: "ph-1",
          current_identity_id: "alice",
          identity_display_name: "Alice Rivera",
          last_seen_at: null,
          active_cameras: [],
        },
      },
      observations: { value: [] },
      keyframes: { value: [] },
      trail: { value: [] },
      coPresent: { value: [] },
      loading: { value: false },
      errors: { value: [] },
      panelErrors: { value: { detail: "", observations: "", keyframes: "", trail: "", coPresent: "" } },
    },
    actions: { fetch: vi.fn() },
  }),
}));

vi.mock("@/composables/usePHLifecycle", () => ({
  usePHLifecycle: () => ({
    state: { saving: { value: false }, lastRevision: { value: null } },
    actions: { apply: vi.fn().mockResolvedValue({ revision: "rev-1" }) },
  }),
}));

vi.mock("@/composables/useNotify", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn() } }),
}));

vi.mock("@/composables/useConfirm", () => ({
  useConfirm: () => ({
    require: vi.fn().mockResolvedValue(true),
    confirmDialog: { value: false },
    confirmTitle: { value: "" },
    confirmText: { value: "" },
    confirmLabel: { value: "Confirm" },
    cancelLabel: { value: "Cancel" },
    confirmColor: { value: "error" },
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  }),
}));

vi.mock("@/composables/useBlurMode", () => ({
  useBlurMode: () => ({ blurMode: { value: false } }),
  useDisplaySrc: () => ({ displaySrc: (src) => src }),
}));

const stubs = {
  "v-card": { template: '<div class="v-card"><slot /></div>', props: ["flat"] },
  "v-card-title": { template: '<div class="v-card-title"><slot /></div>' },
  "v-card-text": { template: '<div class="v-card-text"><slot /></div>' },
  "v-card-actions": { template: '<div class="v-card-actions"><slot /></div>' },
  "v-btn": { template: '<button @click="$emit(\'click\', $event)"><slot /></button>', props: ["icon", "size", "variant", "color"] },
  "v-alert": { template: "<div><slot /></div>" },
  "v-chip": { template: "<span><slot /></span>", props: ["color", "size", "variant"] },
  "v-divider": { template: "<hr />" },
  "v-icon": { template: "<i><slot /></i>", props: ["start", "size"] },
  "v-progress-linear": { template: "<div />" },
  "v-progress-circular": { template: "<div />", props: ["indeterminate", "size", "color"] },
  "v-spacer": { template: "<span />" },
  "v-dialog": { template: '<div v-if="modelValue"><slot /></div>', props: ["modelValue", "maxWidth"] },
  "v-img": {
    template: '<img :src="src" />',
    props: ["src", "maxHeight", "contain"],
  },
  PHPosteriorPanel: true,
  PHKeyframeStrip: true,
  PHObservationsTimeline: true,
  PHTrailMiniFloorPlan: true,
  PHLifecycleActions: true,
  IdentityCorrectionWorkflow: true,
  PHRevisionsFeed: true,
  PHListPanel: true,
};

function mountDrawer(props = {}) {
  return mount(PHInspectorDrawer, {
    props: { phId: "ph-1", mode: "view", identities: [], ...props },
    global: { stubs },
  });
}

describe("PHInspectorDrawer", () => {
  it("renders without console.log calls", () => {
    const consoleSpy = vi.spyOn(console, "log");
    mountDrawer();
    expect(consoleSpy).not.toHaveBeenCalled();
  });

  it("renders display names from the BFF", () => {
    const wrapper = mountDrawer();
    expect(wrapper.text()).toContain("Alice Rivera");
  });

  it("does not render missing posterior evidence as 0%", () => {
    const wrapper = mountDrawer();
    expect(wrapper.text()).not.toContain("alice 0%");
  });

  it("mounts the shared IdentityCorrectionWorkflow in correct mode", async () => {
    const wrapper = mountDrawer({ mode: "correct" });
    expect(wrapper.findComponent(IdentityCorrectionWorkflowStub).exists()).toBe(true);
  });

  it("emits apply when the workflow reports a completed correction", async () => {
    const wrapper = mountDrawer({ mode: "correct" });
    const workflow = wrapper.findComponent(IdentityCorrectionWorkflowStub);
    await workflow.vm.$emit("applied");
    expect(wrapper.emitted("apply")).toBeTruthy();
  });
});

// Resolve the stubbed child by name for findComponent.
const IdentityCorrectionWorkflowStub = { name: "IdentityCorrectionWorkflow" };
