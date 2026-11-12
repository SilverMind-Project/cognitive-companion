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
    x1: 10,
    y1: 20,
    x2: 110,
    y2: 220,
    frame_width: 1920,
    frame_height: 1080,
    effective_identity_id: "amma",
    authority: "direct_face",
    decision_source: "face",
    conflict: false,
    ...over,
  };
}

function mountOverlay(bboxes, props = {}) {
  return mount(IdentityBboxOverlay, {
    props: { imageUrl: "img.jpg", bboxes, targets: TARGETS, ...props },
  });
}

/** Pretend the overlay is rendered *px* wide, then re-measure. */
async function renderAt(wrapper, px) {
  Object.defineProperty(wrapper.find(".overlay-wrap").element, "clientWidth", {
    configurable: true,
    value: px,
  });
  await wrapper.find("img").trigger("load");
}

describe("IdentityBboxOverlay", () => {
  it("renders one labeled box per bbox, both identities visible", () => {
    const w = mountOverlay([
      bbox(),
      bbox({ bbox_id: "b2", ph_id: "ph-b", effective_identity_id: "appa" }),
    ]);
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

  it("sizes label text in screen pixels, not frame pixels", async () => {
    const w = mountOverlay([bbox()]);

    // A 1920px frame shown 640px wide: 3 frame units per screen pixel, so 14px text is 42 units.
    await renderAt(w, 640);
    expect(Number(w.find("text").attributes("font-size"))).toBeCloseTo(42);

    // The same frame shown at full width needs no scaling.
    await renderAt(w, 1920);
    expect(Number(w.find("text").attributes("font-size"))).toBeCloseTo(14);
  });

  it("draws the label with the camera-feed halo at weight 500", () => {
    const w = mountOverlay([bbox()]);
    const text = w.find("text");
    expect(text.attributes("paint-order")).toBe("stroke");
    expect(text.attributes("stroke")).toBeTruthy();
    expect(text.classes()).toContain("overlay-label");
  });

  it("makes the whole box a hit target, and none when not selectable", () => {
    const selectable = mountOverlay([bbox()]);
    expect(selectable.find(".bbox-rect").attributes("pointer-events")).toBe("all");

    const readOnly = mountOverlay([bbox()], { selectable: false });
    expect(readOnly.find(".bbox-rect").attributes("pointer-events")).toBe("none");
  });

  it("draws smaller boxes last so a nested box stays clickable", () => {
    const w = mountOverlay([
      bbox({ bbox_id: "small", x1: 40, y1: 40, x2: 60, y2: 80 }),
      bbox({ bbox_id: "large", x1: 0, y1: 0, x2: 400, y2: 600 }),
    ]);
    const labels = w.findAll(".bbox-group").map((g) => g.attributes("aria-label"));
    expect(labels).toHaveLength(2);
    const rects = w.findAll(".bbox-rect").map((r) => Number(r.attributes("width")));
    expect(rects).toEqual([400, 20]);
  });

  it("highlights the selected box", () => {
    const w = mountOverlay(
      [bbox(), bbox({ bbox_id: "b2", ph_id: "ph-b", effective_identity_id: "appa" })],
      { selectedId: "b2" },
    );
    const selected = w.findAll(".bbox-group.selected");
    expect(selected).toHaveLength(1);
    expect(selected[0].attributes("aria-pressed")).toBe("true");
  });

  it("keeps the boxes selectable when the frame image fails to load", async () => {
    const w = mountOverlay([bbox()]);
    await w.find("img").trigger("error");

    expect(w.find("img").exists()).toBe(false);
    expect(w.text()).toContain("Frame image unavailable");
    await w.find(".bbox-group").trigger("click");
    expect(w.emitted("select")).toBeTruthy();
  });
});
