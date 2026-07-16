/**
 * M08: pure formatters for server-owned identity provenance.
 *
 * These translate the server's per-bbox provenance fields into display labels.
 * They derive NO authority, confidence, or conflict -- those are computed
 * upstream. Raw ArcFace similarity is never turned into a confidence percentage;
 * only the server's `calibrated_confidence` is shown as a percent, and operator
 * authority shows the word "Verified".
 */

/** Human label + mdi icon for a bbox's decision source / authority. */
export function sourceBadge(bbox = {}) {
  if (bbox.conflict) return { label: "Conflict", icon: "mdi-alert", tone: "error" };
  if (bbox.authority === "operator") {
    return { label: "Operator", icon: "mdi-account-check", tone: "success" };
  }
  const source = bbox.decision_source;
  if (source === "face") {
    // "direct_face" is the resolver's bounded IdentityAuthority vocabulary value for a
    // calibrated, authoritative ArcFace commit (M07/F9) -- never an identity id or the
    // decision_source string "arcface_authority".
    return bbox.authority === "direct_face"
      ? { label: "ArcFace", icon: "mdi-face-recognition", tone: "info" }
      : { label: "ArcFace / Uncalibrated", icon: "mdi-face-recognition", tone: "warning" };
  }
  if (source === "reid") return { label: "ReID", icon: "mdi-human", tone: "info" };
  if (source === "temporal_prior" || source === "prior") {
    return { label: "Prior", icon: "mdi-history", tone: "neutral" };
  }
  return { label: source || "Unknown", icon: "mdi-help-circle-outline", tone: "neutral" };
}

/**
 * Confidence reading for display. Operator authority is "Verified" (never a
 * fabricated number). Otherwise the server's calibrated decision confidence as
 * a percent, or a dash when the decision was not calibrated.
 */
export function confidenceLabel(bbox = {}) {
  if (bbox.authority === "operator") return "Verified";
  const c = bbox.calibrated_confidence;
  if (typeof c === "number" && Number.isFinite(c)) return `${Math.round(c * 100)}%`;
  return "—"; // em dash placeholder, not a fabricated value
}

/** Display label for an identity id, preferring a roster display name. */
export function identityLabel(identityId, targets = []) {
  if (!identityId) return "Unknown";
  const match = targets.find((t) => t.identity_id === identityId);
  return match?.display_name || identityId;
}
