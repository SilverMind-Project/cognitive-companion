import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { computed, reactive } from "vue";
import AttestedFacesPanel from "@/components/identity/AttestedFacesPanel.vue";

const stubs = {
  "v-alert": { template: "<div class='v-alert'><slot /><slot name='append' /></div>" },
  "v-btn": {
    template:
      "<button :disabled='disabled' :title='title' @click=\"$emit('click')\"><slot /></button>",
    props: ["disabled", "title"],
    emits: ["click"],
  },
  "v-chip": { template: "<span class='v-chip'><slot /></span>", props: ["color"] },
  "v-progress-circular": { template: "<div />" },
  "v-progress-linear": { template: "<div />", props: ["modelValue"] },
  "v-row": { template: "<div><slot /></div>" },
  "v-col": { template: "<div><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
};

function face(id: string, extra: Record<string, unknown> = {}) {
  return {
    candidate_id: id,
    captured_at: "2026-11-20T09:00:00Z",
    camera_id: "cam-1",
    crop_url: null,
    quality_score: 0.6,
    quality_version: "heuristic-v1",
    yaw_deg: 0,
    pitch_deg: 0,
    nearest_similarity: 0.3,
    label_state: "attested",
    label_kind: "member",
    label_identity_id: "amma",
    attestation_grade: "trajectory",
    promotion_eligible: true,
    promoted: false,
    pose_bin: "left",
    ...extra,
  };
}

function makeAudit(sample = [face("s1")]) {
  const state = reactive({
    sample,
    index: 0,
    exemplars: [face("g1"), face("g2", { promotion_eligible: false, promoted: true })],
    summary: {
      attested: 9,
      audited: 4,
      correct: 3,
      wrong: 1,
      not_a_face: 0,
      precision_lower_bound: 0.3,
      min_audited: 200,
      min_precision_lower_bound: 0.99,
      meets_bar: false,
    },
    loading: false,
    error: "",
    forbidden: false,
    acting: false,
  });
  const current = computed(() => state.sample[state.index] ?? null);
  const actions = {
    load: vi.fn(),
    audit: vi.fn(),
    promote: vi.fn(),
    next: vi.fn(),
    previous: vi.fn(),
  };
  return { state, current, actions };
}

function mountPanel(audit = makeAudit(), keysEnabled = true) {
  return mount(AttestedFacesPanel, {
    attachTo: document.body,
    props: {
      audit: audit as never,
      residentName: (id: string) => (id === "amma" ? "Amma" : id),
      keysEnabled,
    },
    global: { stubs },
  });
}

describe("AttestedFacesPanel", () => {
  it("shows what the wearable claims, how sure it is, and the audit progress", () => {
    const wrapper = mountPanel();
    const text = wrapper.get("[data-test=audit-current]").text();
    expect(text).toContain("Amma");
    expect(text).toContain("path matched");
    expect(wrapper.get("[data-test=audit-bound]").text()).toContain("30.0%");
    expect(wrapper.get("[data-test=audit-bar-chip]").text()).toBe(
      "Not yet trusted for calibration",
    );
    wrapper.unmount();
  });

  it("audits by key and by click, and ignores keys while a dialog is open", async () => {
    const audit = makeAudit();
    const wrapper = mountPanel(audit);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "c" }));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "x" }));
    await wrapper.get("[data-test=audit-wrong]").trigger("click");
    expect(audit.actions.audit.mock.calls.map((c) => c[0])).toEqual([
      "correct",
      "not_a_face",
      "wrong",
    ]);
    wrapper.unmount();

    const quiet = makeAudit();
    const blocked = mountPanel(quiet, false);
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "c" }));
    expect(quiet.actions.audit).not.toHaveBeenCalled();
    blocked.unmount();
  });

  it("offers promotion only for eligible faces and leaves the decision to the parent", async () => {
    const wrapper = mountPanel();
    expect(wrapper.get("[data-test=promote-g2]").attributes("disabled")).toBeDefined();
    await wrapper.get("[data-test=promote-g1]").trigger("click");
    expect(wrapper.emitted("promote")?.[0]?.[0]).toMatchObject({ candidate_id: "g1" });
    wrapper.unmount();
  });

  it("says when nothing waits to be audited", () => {
    const wrapper = mountPanel(makeAudit([]));
    expect(wrapper.find("[data-test=audit-empty]").exists()).toBe(true);
    wrapper.unmount();
  });
});
