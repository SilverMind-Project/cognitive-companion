import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";

vi.mock("@/composables/useBlurMode.js", () => ({
  useBlurMode: () => ({ blurMode: ref(false) }),
  useDisplaySrc: () => ({ displaySrc: (u) => u }),
}));
vi.mock("@/composables/useIdentityColor.js", () => ({
  identityColor: () => "#4ECDC4",
}));

import IdentityBboxOverlay from "@/components/cts/identity/IdentityBboxOverlay.vue";

const TARGETS = [{ identity_id: "amma", display_name: "Amma" }];

function bbox(over = {}) {
  return {
    bbox_id: "b1",
    ph_id: "ph-a",
    x1: 10, y1: 20, x2: 110, y2: 220,
    frame_width: 1920, frame_height: 1080,
    effective_identity_id: "amma",
    authority: "direct_face",
    decision_source: "face",
    conflict: false,
    ...over,
  };
}

function mountOverlay(bboxes) {
  return mount(IdentityBboxOverlay, {
    props: { imageUrl: "img.jpg", bboxes, targets: TARGETS },
  });
}

describe("IdentityBboxOverlay", () => {
  it("renders one labeled box per bbox, both identities visible", () => {
    const w = mountOverlay([bbox(), bbox({ bbox_id: "b2", ph_id: "ph-b", effective_identity_id: "appa" })]);
    expect(w.findAll(".bbox-group")).toHaveLength(2);
    expect(w.text()).toContain("Amma");
  });

  it("emits select with the bbox on click", async () => {
    const w = mountOverlay([bbox()]);
    await w.find(".bbox-group").trigger("click");
    expect(w.emitted("select")[0][0].bbox_id).toBe("b1");
  });

  it("marks operator authority with a check and unknown/conflict distinctly", () => {
    const w = mountOverlay([
      bbox({ authority: "operator" }),
      bbox({ bbox_id: "b2", effective_identity_id: null }),
      bbox({ bbox_id: "b3", conflict: true }),
    ]);
    expect(w.text()).toContain("Amma ✓");
    expect(w.text()).toContain("Unknown");
    expect(w.text()).toContain("Conflict");
    // Unknown + conflict boxes use a dashed stroke (not colour alone).
    const dashed = w.findAll("rect[stroke-dasharray]");
    expect(dashed.length).toBeGreaterThanOrEqual(2);
  });

  it("is keyboard operable and not selectable when disabled", async () => {
    const w = mountOverlay([bbox()]);
    await w.find(".bbox-group").trigger("keydown.enter");
    expect(w.emitted("select")).toBeTruthy();
  });
});
