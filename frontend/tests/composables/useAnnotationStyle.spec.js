/**
 * M1 regression guard: useAnnotationStyle token reads.
 *
 * Two goals:
 *  1. Token-read: when a CSS token is set on the document root, the helpers
 *     return the token value, not the hardcoded fallback.
 *  2. Fallback-parity: when NO tokens are set (jsdom default), every returned
 *     color equals the exact pre-refactor hardcoded hex. This ensures ccDark /
 *     ccLight are visually unchanged after the M1 refactor.
 */
import { describe, it, expect, afterEach } from "vitest";
import { HALO, MAP_LABEL, postureColor } from "@/composables/useAnnotationStyle.js";

const PRIOR = {
  haloCamera: "rgba(0,0,0,0.70)",
  haloLight: "rgba(255,255,255,0.92)",
  annotationInk: "#1e293b",
  standing: "#4ade80",
  sitting: "#fbbf24",
  walking: "#60a5fa",
  lying: "#c084fc",
};

function setToken(name, value) {
  document.documentElement.style.setProperty(name, value);
}
function clearTokens() {
  [
    "--cc-annotation-halo",
    "--cc-annotation-halo-light",
    "--cc-annotation-ink",
    "--cc-posture-standing",
    "--cc-posture-sitting",
    "--cc-posture-walking",
    "--cc-posture-lying",
    "--cc-text-2",
  ].forEach((t) => document.documentElement.style.removeProperty(t));
}

describe("HALO", () => {
  afterEach(clearTokens);

  it("returns fallback color when token is unset (regression guard)", () => {
    expect(HALO.color).toBe(PRIOR.haloCamera);
  });

  it("returns token value when --cc-annotation-halo is set", () => {
    setToken("--cc-annotation-halo", "#SENTINEL-HALO");
    expect(HALO.color).toBe("#SENTINEL-HALO");
  });

  it("attrs() spreads the current color into stroke", () => {
    setToken("--cc-annotation-halo", "#SENTINEL-CAMERA");
    const attrs = HALO.attrs(4);
    expect(attrs.stroke).toBe("#SENTINEL-CAMERA");
    expect(attrs["stroke-width"]).toBe(4);
    expect(attrs["paint-order"]).toBe("stroke");
  });
});

describe("MAP_LABEL", () => {
  afterEach(clearTokens);

  it("fill fallback equals prior hardcoded value when token is unset", () => {
    expect(MAP_LABEL.fill).toBe(PRIOR.annotationInk);
  });

  it("haloColor fallback equals prior hardcoded value when token is unset", () => {
    expect(MAP_LABEL.haloColor).toBe(PRIOR.haloLight);
  });

  it("fill returns token value when --cc-annotation-ink is set", () => {
    setToken("--cc-annotation-ink", "#SENTINEL-INK");
    expect(MAP_LABEL.fill).toBe("#SENTINEL-INK");
  });

  it("haloColor returns token value when --cc-annotation-halo-light is set", () => {
    setToken("--cc-annotation-halo-light", "#SENTINEL-HALO-LIGHT");
    expect(MAP_LABEL.haloColor).toBe("#SENTINEL-HALO-LIGHT");
  });

  it("attrs() spreads fill and haloColor into the attribute object", () => {
    setToken("--cc-annotation-ink", "#SENTINEL-INK");
    setToken("--cc-annotation-halo-light", "#SENTINEL-HALO-L");
    const attrs = MAP_LABEL.attrs(3);
    expect(attrs.fill).toBe("#SENTINEL-INK");
    expect(attrs.stroke).toBe("#SENTINEL-HALO-L");
    expect(attrs["stroke-width"]).toBe(3);
  });

  it("attrs() called twice with different tokens returns fresh values each time", () => {
    setToken("--cc-annotation-ink", "#INK-A");
    const first = MAP_LABEL.attrs().fill;
    setToken("--cc-annotation-ink", "#INK-B");
    const second = MAP_LABEL.attrs().fill;
    expect(first).toBe("#INK-A");
    expect(second).toBe("#INK-B");
  });
});

describe("postureColor", () => {
  afterEach(clearTokens);

  it.each([
    ["standing", PRIOR.standing, "--cc-posture-standing"],
    ["sitting", PRIOR.sitting, "--cc-posture-sitting"],
    ["walking", PRIOR.walking, "--cc-posture-walking"],
    ["lying", PRIOR.lying, "--cc-posture-lying"],
  ])("%s fallback equals prior hex when token is unset", (posture, expected) => {
    expect(postureColor(posture)).toBe(expected);
  });

  it("returns token value when the posture token is set", () => {
    setToken("--cc-posture-standing", "#SENTINEL-STANDING");
    expect(postureColor("standing")).toBe("#SENTINEL-STANDING");
  });

  it("unknown posture returns --cc-text-2 token (or empty string when unset)", () => {
    const result = postureColor("flying");
    expect(typeof result).toBe("string");
  });
});
