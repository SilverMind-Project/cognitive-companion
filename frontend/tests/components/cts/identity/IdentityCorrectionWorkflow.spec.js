import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { ref } from "vue";

vi.mock("@/composables/useNotify.js", () => ({
  useNotify: () => ({ notify: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }),
}));
vi.mock("@/services/timezone.js", () => ({ formatDateTime: (v) => v || "" }));
vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (u) => u }),
}));

import IdentityCorrectionWorkflow from "@/components/cts/identity/IdentityCorrectionWorkflow.vue";

const PROPOSAL = {
  ph_id: "ph-1",
  observation_ids: ["o1", "o2"],
  start: { observation_id: "o1", captured_at: "2026-06-20T12:00:00Z", reason: "segment_edge" },
  end: { observation_id: "o2", captured_at: "2026-06-20T12:00:05Z", reason: "segment_edge" },
  ph_version: 3,
  effective_identity_id: "amma",
};

function makeController(overrides = {}) {
  const state = {
    targets: ref([
      { identity_id: "amma", display_name: "Amma" },
      { identity_id: "appa", display_name: "Appa" },
    ]),
    targetsLoading: ref(false),
    targetsError: ref(""),
    galleryAvailable: ref(true),
    proposal: ref(PROPOSAL),
    proposalLoading: ref(false),
    proposalError: ref(""),
    applying: ref(false),
    staleConflict: ref(false),
    job: ref(null),
    jobPolling: ref(false),
    ...overrides.state,
  };
  const actions = {
    loadTargets: vi.fn().mockResolvedValue(state.targets.value),
    propose: vi.fn().mockResolvedValue(PROPOSAL),
    apply: vi.fn().mockResolvedValue({ revision_id: "rev-1", job_status: "applying" }),
    compensate: vi.fn(),
    refreshJob: vi.fn(),
    pollJob: vi.fn().mockImplementation(async () => {
      state.job.value = {
        revision_id: "rev-1",
        status: "completed",
        required_projections: ["cc"],
        row_counts: { cc: 2 },
        attempts: 1,
      };
      return state.job.value;
    }),
    reset: vi.fn(),
    ...overrides.actions,
  };
  return { state, actions };
}

const stubs = {
  "v-progress-circular": { template: "<div />" },
  "v-alert": { template: "<div class='v-alert'><slot /></div>", props: ["type"] },
  "v-spacer": { template: "<span />" },
  // No explicit @click emit: the parent's @click falls through to the native
  // button so a single user click fires the handler exactly once.
  "v-btn": {
    template: "<button :disabled='disabled'><slot /></button>",
    props: ["disabled", "loading", "color", "variant"],
  },
  "v-autocomplete": {
    template:
      "<input class='ac' :value='modelValue' @input=\"$emit('update:modelValue', $event.target.value || null)\" />",
    props: ["modelValue", "items"],
  },
  "v-select": { template: "<select><slot /></select>", props: ["modelValue", "items"] },
  "v-textarea": { template: "<textarea />", props: ["modelValue"] },
  "v-checkbox": { template: "<input type='checkbox' />", props: ["modelValue"] },
  IdentityEvidenceBadges: {
    template: "<div class='badges' />",
    props: ["bbox", "targets", "detailed"],
  },
  CorrectionRangeSelector: {
    template: "<div class='range' />",
    props: ["proposal", "observations", "scopeMode", "allowFrameOnly", "startId", "endId"],
  },
  CorrectionJobStatus: {
    template: "<div class='job' :data-status='job.status' />",
    props: ["job"],
  },
};

function mountWorkflow(props = {}, controller = makeController()) {
  return mount(IdentityCorrectionWorkflow, {
    props: { phId: "ph-1", controller, ...props },
    global: { stubs },
  });
}

beforeEach(() => vi.clearAllMocks());

describe("IdentityCorrectionWorkflow", () => {
  it("loads targets and proposes on mount", async () => {
    const c = makeController();
    mountWorkflow({}, c);
    await flushPromises();
    expect(c.actions.loadTargets).toHaveBeenCalled();
    expect(c.actions.propose).toHaveBeenCalled();
  });

  it("disables Apply with no target; an empty selection is not a correction", async () => {
    const w = mountWorkflow();
    await flushPromises();
    const applyBtn = w.find("[data-testid='apply-correction']");
    expect(applyBtn.attributes("disabled")).toBeDefined();
    await applyBtn.trigger("click");
    // submit guard returns early -> apply never called
    expect(w.props("controller").actions.apply).not.toHaveBeenCalled();
  });

  it("Set to Unknown submits an explicit null target via a typed action", async () => {
    const c = makeController();
    const w = mountWorkflow({}, c);
    await flushPromises();
    await w.find("[data-testid='set-unknown']").trigger("click");
    await flushPromises();
    expect(c.actions.apply).toHaveBeenCalledTimes(1);
    const payload = c.actions.apply.mock.calls[0][0];
    expect(payload.set_unknown).toBe(true);
    expect(payload.target_identity_id).toBeNull();
  });

  it("applies a selected identity and emits applied only after the job completes", async () => {
    const c = makeController();
    const w = mountWorkflow({}, c);
    await flushPromises();
    await w.find("input.ac").setValue("amma");
    await w.find("[data-testid='apply-correction']").trigger("click");
    await flushPromises();
    const payload = c.actions.apply.mock.calls[0][0];
    expect(payload.target_identity_id).toBe("amma");
    expect(payload.set_unknown).toBe(false);
    expect(payload.base_ph_version).toBe(3);
    expect(c.actions.pollJob).toHaveBeenCalledWith("rev-1");
    expect(w.emitted("applied")).toBeTruthy();
  });

  it("does not emit applied while the job is still applying", async () => {
    const c = makeController({
      actions: {
        pollJob: vi.fn().mockImplementation(async function () {
          c.state.job.value = {
            revision_id: "rev-1",
            status: "applying",
            required_projections: ["cc"],
            row_counts: {},
            attempts: 0,
          };
          return c.state.job.value;
        }),
      },
    });
    const w = mountWorkflow({}, c);
    await flushPromises();
    await w.find("input.ac").setValue("amma");
    await w.find("[data-testid='apply-correction']").trigger("click");
    await flushPromises();
    expect(w.emitted("applied")).toBeFalsy();
  });

  it("shows the stale-conflict banner when the version changed", async () => {
    const c = makeController({ state: { staleConflict: ref(true) } });
    const w = mountWorkflow({}, c);
    await flushPromises();
    expect(w.find("[data-testid='stale-conflict']").exists()).toBe(true);
  });

  it("renders the empty-household state when no targets", async () => {
    const c = makeController({ state: { targets: ref([]) } });
    const w = mountWorkflow({}, c);
    await flushPromises();
    expect(w.find("[data-testid='apply-correction']").exists()).toBe(false);
    expect(w.text()).toContain("No active household members");
  });

  it("hides the ReID verify action when the server returns no eligibility", async () => {
    const w = mountWorkflow({ bbox: { effective_identity_id: "amma", authority: "operator" } });
    await flushPromises();
    expect(w.find("input[type='checkbox']").exists()).toBe(false);
  });
});
