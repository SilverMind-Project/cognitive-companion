import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import MaraudersFootprintGlyph from "@/components/marauders/MaraudersFootprintGlyph.vue";

describe("MaraudersFootprintGlyph", () => {
  it("renders the shared footstep SVG asset by fragment reference", () => {
    const wrapper = mount(MaraudersFootprintGlyph);
    const href = wrapper.find("use").attributes("href");

    expect(href).toContain("footstep.svg");
    expect(href.endsWith("#marauders-footstep")).toBe(true);
  });

  it("passes transform, opacity, and fill to the glyph group", () => {
    const wrapper = mount(MaraudersFootprintGlyph, {
      props: {
        transform: "translate(20 30) rotate(45)",
        opacity: 0.6,
        fill: "var(--cc-annotation-ink)",
      },
    });

    expect(wrapper.attributes("transform")).toBe("translate(20 30) rotate(45)");
    expect(wrapper.attributes("opacity")).toBe("0.6");
    expect(wrapper.attributes("fill")).toBe("var(--cc-annotation-ink)");
  });

  it("mirrors right-foot glyphs without changing the shared asset", () => {
    const wrapper = mount(MaraudersFootprintGlyph, {
      props: { mirrored: true },
    });

    expect(wrapper.find("g > g").attributes("transform")).toBe("scale(-1 1)");
  });
});
