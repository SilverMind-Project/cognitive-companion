import { mount } from "@vue/test-utils";
import { describe, it, expect, vi } from "vitest";
import PHInspectorDrawer from "../PHInspectorDrawer.vue";

// Mock composables
vi.mock("@/composables/usePHDetail", () => ({
  usePHDetail: () => ({
    state: {
      detail: { value: { ph_id: "ph-1", current_identity_id: "alice", last_seen_at: null, active_cameras: [] } },
      observations: { value: [] },
      keyframes: { value: [] },
      trail: { value: [] },
      coPresent: { value: [] },
      loading: { value: false },
      errors: { value: [] },
    },
    actions: { fetch: vi.fn() },
  }),
}));

vi.mock("@/composables/usePHCorrection", () => ({
  usePHCorrection: () => ({
    state: { saving: { value: false }, lastRevision: { value: null } },
    actions: { apply: vi.fn().mockResolvedValue({ revision: "rev-1" }) },
  }),
}));

vi.mock("@/composables/useNotify", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn() } }),
}));

vi.mock("@/composables/useConfirm", () => ({
  useConfirm: () => ({ require: vi.fn().mockResolvedValue(true) }),
}));

const stubs = {
  "v-btn": { template: '<button @click="$emit(\'click\', $event)"><slot /></button>' },
  "v-chip": { template: "<span><slot /></span>", props: ["color", "size", "variant"] },
  "v-divider": { template: "<hr />" },
  "v-icon": { template: "<i><slot /></i>" },
  "v-progress-linear": { template: "<div />" },
  "v-spacer": { template: "<span />" },
  PHPosteriorPanel: true,
  PHObservationsTimeline: true,
  PHTrailMiniFloorPlan: true,
  PHCorrectionForm: true,
  PHRevisionsFeed: true,
  PHListPanel: true,
};

function mountDrawer() {
  return mount(PHInspectorDrawer, {
    props: { phId: "ph-1", mode: "view", identities: [] },
    global: { stubs },
  });
}

describe("PHInspectorDrawer", () => {
  it("renders without console.log calls", () => {
    const consoleSpy = vi.spyOn(console, "log");
    mountDrawer();
    expect(consoleSpy).not.toHaveBeenCalled();
  });

  it("does not use console.error for notifications", () => {
    const spy = vi.spyOn(console, "error");
    mountDrawer();
    expect(spy).not.toHaveBeenCalledWith(expect.stringContaining("[ph-drawer]"));
  });
});
