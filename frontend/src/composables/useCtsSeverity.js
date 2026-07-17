/**
 * CTS severity display utilities.
 *
 * Replaces duplicated ``function severityColor(severity)`` definitions across
 * the admin CTS views.
 */

const SEVERITY_COLORS = { info: "grey", warning: "orange", emergency: "red" };

export function severityColor(severity) {
  return SEVERITY_COLORS[severity] || "grey";
}
