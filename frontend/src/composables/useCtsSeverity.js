/**
 * CTS severity display utilities.
 *
 * Replaces duplicated ``function severityColor(severity)`` definitions in
 * CTSDashboardView, CTSSignalsView, and CTSKeyframesView.
 */

const SEVERITY_COLORS = { info: "grey", warning: "orange", emergency: "red" };

const SEVERITY_ICONS = {
  info: "mdi-information",
  warning: "mdi-alert",
  emergency: "mdi-alert-circle",
};

export function severityColor(severity) {
  return SEVERITY_COLORS[severity] || "grey";
}

export function severityIcon(severity) {
  return SEVERITY_ICONS[severity] || "mdi-circle";
}
