import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import IdentityEvidenceBadges from "@/components/cts/identity/IdentityEvidenceBadges.vue";

const stubs = {
  "v-chip": { template: "<span class='chip'><slot /></span>", props: ["color", "size", "variant", "prependIcon"] },
  "v-divider": { template: "<hr />" },
};

const TARGETS = [{ identity_id: "amma", display_name: "Amma" }];

function mountBadges(bbox, detailed = false) {
  return mount(IdentityEvidenceBadges, {
    props: { bbox, targets: TARGETS, detailed },
    global: { stubs },
  });
}

describe("IdentityEvidenceBadges", () => {
  it("shows Verified for operator authority, never a percent", () => {
    const w = mountBadges({ authority: "operator", effective_identity_id: "amma", calibrated_confidence: 0.9 });
    expect(w.text()).toContain("Verified");
    expect(w.text()).not.toContain("90%");
  });

  it("shows calibrated confidence as a percent for non-operator decisions", () => {
    const w = mountBadges({ authority: "direct_face", decision_source: "face", effective_identity_id: "amma", calibrated_confidence: 0.77 });
    expect(w.text()).toContain("77%");
  });

  it("renders raw ArcFace similarity only as 'Raw similarity', never as confidence", () => {
    const w = mountBadges(
      {
        authority: "direct_face",
        decision_source: "face",
        effective_identity_id: "amma",
        inferred_identity_id: "amma",
        calibrated_confidence: 0.6,
        raw_similarity: 0.842,
      },
      true
    );
    expect(w.text()).toContain("Raw similarity");
    expect(w.text()).toContain("0.842");
    // The raw similarity is never formatted as a percent.
    expect(w.text()).not.toContain("84%");
  });

  it("shows inferred versus effective identity when they differ", () => {
    const w = mountBadges(
      { authority: "operator", effective_identity_id: "amma", inferred_identity_id: "ghost" },
      true
    );
    expect(w.text()).toContain("Effective");
    expect(w.text()).toContain("Inferred");
    expect(w.text()).toContain("Amma");
    expect(w.text()).toContain("ghost");
  });

  it("surfaces a pending-review chip", () => {
    const w = mountBadges({ authority: "direct_face", decision_source: "face", effective_identity_id: "amma", pending_review: true });
    expect(w.text()).toContain("Pending review");
  });
});
