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
  r.style.setProperty("--cc-chart-1", "#SENTINEL-CHART1-DARK");
  r.style.setProperty("--cc-chart-2", "#SENTINEL-CHART2-DARK");
  r.style.setProperty("--cc-chart-3", "#SENTINEL-CHART3-DARK");
  r.style.setProperty("--cc-chart-4", "#SENTINEL-CHART4-DARK");
  r.style.setProperty("--cc-chart-5", "#SENTINEL-CHART5-DARK");
  r.style.setProperty("--cc-chart-6", "#SENTINEL-CHART6-DARK");
  r.style.setProperty("--cc-brand", "#SENTINEL-BRAND-DARK");
  r.style.setProperty("--cc-success", "#SENTINEL-SUCCESS-DARK");
  r.style.setProperty("--cc-warning", "#SENTINEL-WARNING-DARK");
  r.style.setProperty("--cc-error", "#SENTINEL-ERROR-DARK");
  r.style.setProperty("--cc-text-1", "#SENTINEL-TEXT1-DARK");
  r.style.setProperty("--cc-text-2", "#SENTINEL-TEXT2-DARK");
  r.style.setProperty("--cc-text-3", "#SENTINEL-TEXT3-DARK");
  r.style.setProperty("--cc-divider", "#SENTINEL-DIVIDER-DARK");
  r.style.setProperty("--cc-bg-elevated", "#SENTINEL-BG-EL-DARK");
  r.style.setProperty("--cc-glass-border", "#SENTINEL-GLASS-DARK");
}

function setLightTokens() {
  const r = document.documentElement;
  r.style.setProperty("--cc-chart-1", "#SENTINEL-CHART1-LIGHT");
  r.style.setProperty("--cc-chart-2", "#SENTINEL-CHART2-LIGHT");
  r.style.setProperty("--cc-chart-3", "#SENTINEL-CHART3-LIGHT");
  r.style.setProperty("--cc-chart-4", "#SENTINEL-CHART4-LIGHT");
  r.style.setProperty("--cc-chart-5", "#SENTINEL-CHART5-LIGHT");
  r.style.setProperty("--cc-chart-6", "#SENTINEL-CHART6-LIGHT");
  r.style.setProperty("--cc-brand", "#SENTINEL-BRAND-LIGHT");
  r.style.setProperty("--cc-success", "#SENTINEL-SUCCESS-LIGHT");
  r.style.setProperty("--cc-warning", "#SENTINEL-WARNING-LIGHT");
  r.style.setProperty("--cc-error", "#SENTINEL-ERROR-LIGHT");
  r.style.setProperty("--cc-text-1", "#SENTINEL-TEXT1-LIGHT");
  r.style.setProperty("--cc-text-2", "#SENTINEL-TEXT2-LIGHT");
  r.style.setProperty("--cc-text-3", "#SENTINEL-TEXT3-LIGHT");
  r.style.setProperty("--cc-divider", "#SENTINEL-DIVIDER-LIGHT");
  r.style.setProperty("--cc-bg-elevated", "#SENTINEL-BG-EL-LIGHT");
  r.style.setProperty("--cc-glass-border", "#SENTINEL-GLASS-LIGHT");
}

function clearTokens() {
  [
    "--cc-chart-1", "--cc-chart-2", "--cc-chart-3", "--cc-chart-4",
    "--cc-chart-5", "--cc-chart-6",
    "--cc-brand", "--cc-success", "--cc-warning", "--cc-error",
    "--cc-text-1", "--cc-text-2", "--cc-text-3",
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

  it("color palette is sourced from --cc-chart-* tokens, not hardcoded hex", () => {
    const { chartTheme } = useChartTheme();
    const palette = chartTheme.value.color;
    expect(Array.isArray(palette)).toBe(true);
    expect(palette.length).toBeGreaterThan(0);
    // Every color in the palette must match one of the DS chart sentinel values
    const sentinels = new Set([
      "#SENTINEL-CHART1-DARK", "#SENTINEL-CHART2-DARK", "#SENTINEL-CHART3-DARK",
      "#SENTINEL-CHART4-DARK", "#SENTINEL-CHART5-DARK", "#SENTINEL-CHART6-DARK",
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
    const darkFirst = chartTheme.value.color[0];
    expect(darkFirst).toBe("#SENTINEL-CHART1-DARK");

    // Simulate theme switch: change token values AND the theme name reactive ref.
    setLightTokens();
    _themeName.value = "ccLight";
    _isDark.value = false;

    const lightFirst = chartTheme.value.color[0];
    expect(lightFirst).toBe("#SENTINEL-CHART1-LIGHT");
    expect(lightFirst).not.toBe(darkFirst);
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
