/**
 * Theme bridge: maps Vuetify/--cc-* tokens to an ECharts theme object.
 *
 * Every chart component calls this composable so charts look native in both
 * light and dark themes. No hardcoded hex colors appear in the returned
 * object — all values are read from getComputedStyle at call time and
 * recomputed whenever the active Vuetify theme changes.
 *
 * Design rule D3: bespoke spatial renderers (floor plan, bbox canvas) read
 * the same token helpers exported here so they share the token vocabulary.
 */
import { computed } from "vue";
import { useTheme } from "vuetify";

/**
 * Read a CSS custom property from the document root.
 * Returns empty string when running outside a browser (SSR / test without DOM).
 */
function token(name) {
  if (typeof document === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Returns { chartTheme } — a computed ECharts theme object derived entirely
 * from the active --cc-* design tokens. Reactive: re-evaluates when the
 * Vuetify theme changes (dark ↔ light) because chartTheme depends on the
 * Vuetify theme reactive ref.
 *
 * @returns {{ chartTheme: import('vue').ComputedRef<object> }}
 */
export function useChartTheme() {
  const vuetifyTheme = useTheme();

  const chartTheme = computed(() => {
    // Access the reactive theme name so this computed re-runs on theme switch.
    // eslint-disable-next-line no-unused-expressions
    vuetifyTheme.name.value;

    const palette = [
      token("--cc-brand"),
      token("--cc-teal"),
      token("--cc-success"),
      token("--cc-warning"),
      token("--cc-indigo"),
      token("--cc-purple"),
      token("--cc-error"),
    ];

    const textPrimary = token("--cc-text-1");
    const textSecondary = token("--cc-text-2");
    const divider = token("--cc-divider");
    const bgElevated = token("--cc-bg-elevated");
    const glassBorder = token("--cc-glass-border");

    const axisCommon = {
      axisLine: { lineStyle: { color: divider } },
      axisTick: { lineStyle: { color: divider } },
      axisLabel: { color: textSecondary },
      splitLine: { lineStyle: { color: divider, type: "dashed" } },
      nameTextStyle: { color: textSecondary },
    };

    return {
      color: palette,
      backgroundColor: "transparent",
      textStyle: { color: textPrimary },

      title: {
        textStyle: { color: textPrimary },
        subtextStyle: { color: textSecondary },
      },
      legend: {
        textStyle: { color: textSecondary },
      },
      tooltip: {
        backgroundColor: bgElevated,
        borderColor: glassBorder,
        textStyle: { color: textPrimary },
      },
      grid: {
        borderColor: divider,
      },
      xAxis: axisCommon,
      yAxis: axisCommon,
      categoryAxis: axisCommon,
      valueAxis: axisCommon,
      timeAxis: axisCommon,

      // Severity tokens for status-driven components (CcDagChart, CcStatusTimeline).
      _severity: {
        pending: textSecondary,
        running: token("--cc-brand"),
        succeeded: token("--cc-success"),
        failed: token("--cc-error"),
        skipped: token("--cc-text-3"),
        info: token("--cc-text-3"),
        warning: token("--cc-warning"),
        error: token("--cc-error"),
      },
    };
  });

  return { chartTheme };
}

/**
 * Read a single --cc-* token by name. Exported for bespoke spatial renderers
 * (floor plan, bbox canvas) so they share the same token vocabulary.
 *
 * @param {string} name  CSS custom property name, e.g. '--cc-brand'
 * @returns {string}
 */
export function ccToken(name) {
  return token(name);
}
