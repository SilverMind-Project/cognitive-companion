/**
 * U3-T4: useChartTheme composable
 *
 * Verifies that the returned theme object:
 * - Sources every color from --cc-* CSS custom properties (no literal hex)
 * - Returns distinct palettes for light vs dark (reactive to theme changes)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ref, computed } from "vue";

// ── Mock vuetify before importing the composable ──────────────────────────

const _themeName = ref("ccDark");
const _isDark = ref(true);

vi.mock("vuetify", () => ({
  useTheme: vi.fn(() => ({
    name: _themeName,
    current: computed(() => ({ dark: _isDark.value })),
  })),
}));

import { useChartTheme, ccToken } from "../../src/composables/useChartTheme.js";

// ── Sentinel helpers ──────────────────────────────────────────────────────

function setDarkTokens() {
  const r = document.documentElement;
  r.style.setProperty("--cc-brand", "#SENTINEL-BRAND-DARK");
  r.style.setProperty("--cc-teal", "#SENTINEL-TEAL-DARK");
  r.style.setProperty("--cc-success", "#SENTINEL-SUCCESS-DARK");
  r.style.setProperty("--cc-warning", "#SENTINEL-WARNING-DARK");
  r.style.setProperty("--cc-error", "#SENTINEL-ERROR-DARK");
  r.style.setProperty("--cc-indigo", "#SENTINEL-INDIGO-DARK");
  r.style.setProperty("--cc-purple", "#SENTINEL-PURPLE-DARK");
  r.style.setProperty("--cc-text-1", "#SENTINEL-TEXT1-DARK");
  r.style.setProperty("--cc-text-2", "#SENTINEL-TEXT2-DARK");
  r.style.setProperty("--cc-text-3", "#SENTINEL-TEXT3-DARK");
  r.style.setProperty("--cc-divider", "#SENTINEL-DIVIDER-DARK");
  r.style.setProperty("--cc-bg-elevated", "#SENTINEL-BG-EL-DARK");
  r.style.setProperty("--cc-glass-border", "#SENTINEL-GLASS-DARK");
}

function setLightTokens() {
  const r = document.documentElement;
  r.style.setProperty("--cc-brand", "#SENTINEL-BRAND-LIGHT");
  r.style.setProperty("--cc-teal", "#SENTINEL-TEAL-LIGHT");
  r.style.setProperty("--cc-success", "#SENTINEL-SUCCESS-LIGHT");
  r.style.setProperty("--cc-warning", "#SENTINEL-WARNING-LIGHT");
  r.style.setProperty("--cc-error", "#SENTINEL-ERROR-LIGHT");
  r.style.setProperty("--cc-indigo", "#SENTINEL-INDIGO-LIGHT");
  r.style.setProperty("--cc-purple", "#SENTINEL-PURPLE-LIGHT");
  r.style.setProperty("--cc-text-1", "#SENTINEL-TEXT1-LIGHT");
  r.style.setProperty("--cc-text-2", "#SENTINEL-TEXT2-LIGHT");
  r.style.setProperty("--cc-text-3", "#SENTINEL-TEXT3-LIGHT");
  r.style.setProperty("--cc-divider", "#SENTINEL-DIVIDER-LIGHT");
  r.style.setProperty("--cc-bg-elevated", "#SENTINEL-BG-EL-LIGHT");
  r.style.setProperty("--cc-glass-border", "#SENTINEL-GLASS-LIGHT");
}

function clearTokens() {
  [
    "--cc-brand", "--cc-teal", "--cc-success", "--cc-warning", "--cc-error",
    "--cc-indigo", "--cc-purple", "--cc-text-1", "--cc-text-2", "--cc-text-3",
    "--cc-divider", "--cc-bg-elevated", "--cc-glass-border",
  ].forEach((t) => document.documentElement.style.removeProperty(t));
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe("useChartTheme", () => {
  beforeEach(() => {
    _themeName.value = "ccDark";
    _isDark.value = true;
    setDarkTokens();
  });

  afterEach(clearTokens);

  it("returns a chartTheme computed ref", () => {
    const { chartTheme } = useChartTheme();
    expect(chartTheme).toBeDefined();
    expect(typeof chartTheme.value).toBe("object");
  });

  it("color palette is sourced from --cc-* tokens, not hardcoded hex", () => {
    const { chartTheme } = useChartTheme();
    const palette = chartTheme.value.color;
    expect(Array.isArray(palette)).toBe(true);
    expect(palette.length).toBeGreaterThan(0);
    // Every color in the palette must match one of the sentinel values we set
    const sentinels = new Set([
      "#SENTINEL-BRAND-DARK", "#SENTINEL-TEAL-DARK", "#SENTINEL-SUCCESS-DARK",
      "#SENTINEL-WARNING-DARK", "#SENTINEL-ERROR-DARK", "#SENTINEL-INDIGO-DARK",
      "#SENTINEL-PURPLE-DARK",
    ]);
    for (const c of palette) {
      expect(sentinels.has(c), `Expected "${c}" to be a sentinel token value`).toBe(true);
    }
  });

  it("textStyle.color comes from --cc-text-1 token", () => {
    const { chartTheme } = useChartTheme();
    expect(chartTheme.value.textStyle.color).toBe("#SENTINEL-TEXT1-DARK");
  });

  it("tooltip.backgroundColor comes from --cc-bg-elevated token", () => {
    const { chartTheme } = useChartTheme();
    expect(chartTheme.value.tooltip.backgroundColor).toBe("#SENTINEL-BG-EL-DARK");
  });

  it("tooltip.borderColor comes from --cc-glass-border token", () => {
    const { chartTheme } = useChartTheme();
    expect(chartTheme.value.tooltip.borderColor).toBe("#SENTINEL-GLASS-DARK");
  });

  it("axis labels use --cc-text-2 token", () => {
    const { chartTheme } = useChartTheme();
    expect(chartTheme.value.xAxis.axisLabel.color).toBe("#SENTINEL-TEXT2-DARK");
  });

  it("returns distinct palettes when token values differ between themes", () => {
    const { chartTheme } = useChartTheme();
    const darkBrand = chartTheme.value.color[0];
    expect(darkBrand).toBe("#SENTINEL-BRAND-DARK");

    // Simulate theme switch: change token values AND the theme name reactive ref.
    setLightTokens();
    _themeName.value = "ccLight";
    _isDark.value = false;

    const lightBrand = chartTheme.value.color[0];
    expect(lightBrand).toBe("#SENTINEL-BRAND-LIGHT");
    expect(lightBrand).not.toBe(darkBrand);
  });

  it("_severity tokens come from CSS vars", () => {
    const { chartTheme } = useChartTheme();
    const sev = chartTheme.value._severity;
    expect(sev.running).toBe("#SENTINEL-BRAND-DARK");
    expect(sev.succeeded).toBe("#SENTINEL-SUCCESS-DARK");
    expect(sev.failed).toBe("#SENTINEL-ERROR-DARK");
    expect(sev.warning).toBe("#SENTINEL-WARNING-DARK");
  });
});

describe("ccToken", () => {
  afterEach(clearTokens);

  it("reads a CSS custom property from document root", () => {
    document.documentElement.style.setProperty("--cc-brand", "#test-val");
    expect(ccToken("--cc-brand")).toBe("#test-val");
  });

  it("returns empty string for an unset property", () => {
    expect(ccToken("--cc-nonexistent-prop")).toBe("");
  });
});
