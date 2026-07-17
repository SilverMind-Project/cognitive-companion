/**
 * CTS (Continuous Tracking System) API client.
 *
 * All calls go through the CC backend BFF: the browser never contacts the
 * tracking microservices directly.
 */

import { getApiKey, requestBlobUrl, requestJson } from "./http";

const BASE = "/api/v1/cts";

/**
 * Requests go through the shared core in `http.ts` (auth, ApiError, network-error wrapping)
 * rather than this module's own copy of that plumbing.
 *
 * Response shapes are no longer hand-declared: they are backend-owned and described by
 * `openapi.json`. Keying these calls to the generated `paths` type is follow-up work.
 */
function req(path, options = {}) {
  return requestJson(`${BASE}${path}`, options);
}

export const cts = {
  // ── Feature flags ──────────────────────────────────────────────────────────
  getStatus: () => req("/status"),
  getFeatures: () => req("/features"),

  // ── Camera roster ──────────────────────────────────────────────────────────
  getCameras: () => req("/cameras"),
  getCamera: (id) => req(`/cameras/${id}`),
  createCamera: (data) => req("/cameras", { method: "POST", body: JSON.stringify(data) }),
  updateCamera: (id, data) => req(`/cameras/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteCamera: (id) => req(`/cameras/${id}`, { method: "DELETE" }),
  testConnect: (rtsp_url) =>
    req("/cameras/test-connect", { method: "POST", body: JSON.stringify({ rtsp_url }) }),
  /** Live camera snapshot as an authenticated object URL. The caller must revoke it. */
  getSnapshot: (id) => requestBlobUrl(`${BASE}/cameras/${encodeURIComponent(id)}/snapshot`),
  getCameraHealth: (id) => req(`/cameras/${id}/health`),
  reloadCamera: (id) => req(`/cameras/${id}/reload`, { method: "POST" }),

  // ── Calibration: health status ──────────────────────────────────────────────
  getCalibrationHealth: () => req("/calibration/health"),

  // ── Calibration: homography ─────────────────────────────────────────────────
  postHomography: (camera_id, points, imageWidth, imageHeight) =>
    req("/calibration/homography", {
      method: "POST",
      body: JSON.stringify({
        camera_id,
        points,
        image_width: imageWidth,
        image_height: imageHeight,
      }),
    }),
  previewHomography: (points) =>
    req("/calibration/homography/preview", {
      method: "POST",
      body: JSON.stringify({ points }),
    }),
  getHomography: (camera_id) => req(`/calibration/homography/${camera_id}`),
  autoCalibrate: (camera_id, body) =>
    req(`/calibration/auto/${camera_id}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  postFloorRegion: (camera_id, polygon, source = "manual") =>
    req(`/calibration/floor_region/${camera_id}`, {
      method: "POST",
      body: JSON.stringify({ polygon, source }),
    }),

  // ── Calibration: privacy zones ──────────────────────────────────────────────
  postPrivacyZones: (camera_id, zones) =>
    req("/calibration/privacy_zones", {
      method: "POST",
      body: JSON.stringify({ camera_id, zones }),
    }),
  getPrivacyZones: (camera_id) => req(`/calibration/privacy_zones/${camera_id}`),

  // ── Calibration: adjacency ──────────────────────────────────────────────────
  postAdjacency: (edges) =>
    req("/calibration/adjacency", { method: "POST", body: JSON.stringify({ edges }) }),
  getAdjacency: () => req("/calibration/adjacency"),

  // ── Overlap groups ──────────────────────────────────────────────────────────
  getVisibilityPolygons: () => req("/calibration/visibility_polygons"),
  recomputeVisibilityPolygons: () =>
    req("/calibration/visibility_polygons/recompute", { method: "POST" }),
  getInferredAdjacency: () => req("/calibration/adjacency/inferred"),
  getOverlapGroups: () => req("/overlap_groups"),

  // ── Calibration diagnostics and transit zones ──────────────────────────────
  getCalibrationDiagnostics: () => req("/diagnostics/calibration"),
  getTransitZones: () => req("/transit-zones"),
  createTransitZone: (body) =>
    req("/transit-zones", { method: "POST", body: JSON.stringify(body) }),
  updateTransitZone: (id, body) =>
    req(`/transit-zones/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteTransitZone: (id) =>
    req(`/transit-zones/${id}`, { method: "DELETE" }),

  // ── Dementia signals ────────────────────────────────────────────────────────
  getSignals: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.person_id) qs.set("person_id", params.person_id);
    if (params.signal_type) qs.set("signal_type", params.signal_type);
    if (params.severity) qs.set("severity", params.severity);
    if (params.window_hours) qs.set("window_hours", params.window_hours);
    if (params.limit) qs.set("limit", params.limit);
    if (params.offset != null) qs.set("offset", params.offset);
    const q = qs.toString();
    return q ? req(`/signals?${q}`) : req("/signals");
  },
  acknowledgeSignal: (signalId, feedback = null) =>
    req(`/signals/${signalId}/ack`, {
      method: "POST",
      body: feedback !== null ? JSON.stringify({ feedback }) : JSON.stringify({}),
    }),
  deleteSignal: (signalId) =>
    req(`/signals/${signalId}`, { method: "DELETE" }),
  batchDeleteSignals: (signalIds) =>
    req("/signals/batch", {
      method: "DELETE",
      body: JSON.stringify({ signal_ids: signalIds }),
    }),
  getUnacknowledged: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.person_id) qs.set("person_id", params.person_id);
    if (params.severity) qs.set("severity", params.severity);
    if (params.window_hours) qs.set("window_hours", params.window_hours);
    if (params.limit) qs.set("limit", params.limit);
    const q = qs.toString();
    return q ? req(`/signals/unacknowledged?${q}`) : req("/signals/unacknowledged");
  },
  getSignalSummary: (personId) => {
    const qs = personId ? `?person_id=${encodeURIComponent(personId)}` : "";
    return req(`/signals/summary${qs}`);
  },
  getSignalTrend: (personId, days = 7) =>
    req(`/signals/trend/${personId}?days=${days}`),

  // ── Tagged keyframes ────────────────────────────────────────────────────────
  getKeyframes: (params = {}) => {
    // M07: grouped physical-frame cards with server-side filters.
    const qs = new URLSearchParams();
    if (params.person_id) qs.set("person_id", params.person_id);
    if (params.camera_id) qs.set("camera_id", params.camera_id);
    if (params.tag_reason) qs.set("tag_reason", params.tag_reason);
    if (params.after) qs.set("after", params.after);
    if (params.before) qs.set("before", params.before);
    if (params.explicit_unknown) qs.set("explicit_unknown", "true");
    if (params.authority) qs.set("authority", params.authority);
    if (params.decision_source) qs.set("decision_source", params.decision_source);
    if (params.conflict_only) qs.set("conflict_only", "true");
    if (params.pending_review_only) qs.set("pending_review_only", "true");
    if (params.limit) qs.set("limit", params.limit);
    if (params.offset) qs.set("offset", params.offset);
    const q = qs.toString();
    return q ? req(`/keyframes?${q}`) : req("/keyframes");
  },
  getKeyframe: (sampleId) => req(`/keyframes/${sampleId}`),
  retainKeyframe: (sampleId) =>
    req(`/keyframes/${sampleId}/retain`, { method: "POST" }),

  /** Fetch a keyframe image as an authenticated blob (object URL).
   *  The caller MUST call URL.revokeObjectURL(url) on unmount. */
  getKeyframeBlob: (minioKey) => {
    // The key is a MinIO path: encode each segment but keep the separators, since the route is
    // declared as {key:path}.
    const encodedKey = minioKey.split("/").map(encodeURIComponent).join("/");
    return requestBlobUrl(`${BASE}/frames/${encodedKey}`);
  },

  // ── Weekly report ──────────────────────────────────────────────────────────
  getWeeklyReport: (personId, weekStart) =>
    req("/reports/weekly", {
      method: "POST",
      body: JSON.stringify({ person_id: personId, week_start: weekStart }),
    }),

  // ── Signal explorer ────────────────────────────────────────────────────────
  getSignalExplorer: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.kind) params.kind.forEach((k) => qs.append("kind[]", k));
    if (params.severity) params.severity.forEach((s) => qs.append("severity[]", s));
    if (params.limit) qs.set("limit", params.limit);
    const q = qs.toString();
    return req(`/signals/explorer${q ? "?" + q : ""}`);
  },
  getSignalEvidence: (signalId) => req(`/signals/${encodeURIComponent(signalId)}/evidence`),

  // ── Dashboard ───────────────────────────────────────────────────────────────
  getDashboardOverview: () => req("/dashboard/overview"),
  getUnacknowledgedCount: () => req("/dashboard/unacknowledged-count"),
  createSuppression: (data) =>
    req("/dashboard/suppressions", { method: "POST", body: JSON.stringify(data) }),
  deleteSuppression: (id) =>
    req(`/dashboard/suppressions/${id}`, { method: "DELETE" }),
  getDashboardSignals: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.person_id) qs.set("person_id", params.person_id);
    if (params.window_hours) qs.set("window_hours", params.window_hours);
    if (params.signal_kind) qs.set("signal_kind", params.signal_kind);
    if (params.limit) qs.set("limit", params.limit);
    const q = qs.toString();
    return q ? req(`/dashboard/signals?${q}`) : req("/dashboard/signals");
  },
  getDashboardTrajectory: (personId, params = {}) => {
    const qs = new URLSearchParams({ person_id: personId });
    if (params.start) qs.set("start", params.start);
    if (params.end) qs.set("end", params.end);
    if (params.limit) qs.set("limit", params.limit);
    return req(`/dashboard/trajectory?${qs.toString()}`);
  },
  getDashboardDwellSummary: (personId, date) => {
    const qs = new URLSearchParams({ person_id: personId });
    if (date) qs.set("date", date);
    return req(`/dashboard/dwell_summary?${qs.toString()}`);
  },

  // ── Identity corrections ──────────────────────────────────────────────────
  getIdentities: () => req("/identity/identities"),
  // Authoritative correction targets (active household members), independent of
  // the ReID gallery. Used for filter options, not page-derived identities.
  getCorrectionTargets: () => req("/identity/correction-targets"),
  applyCorrection: (payload) =>
    req("/identity/corrections", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  mergeIdentities: (payload) =>
    req("/identity/merges", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  batchCorrect: (corrections) =>
    req("/identity/corrections/batch", {
      method: "POST",
      body: JSON.stringify({ corrections }),
    }),
  getDecisions: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.kind) qs.set("kind", params.kind);
    if (params.limit) qs.set("limit", params.limit);
    if (params.before_id) qs.set("before_id", params.before_id);
    const q = qs.toString();
    return q ? req(`/identity/decisions?${q}`) : req("/identity/decisions");
  },
  getRevisions: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.window_hours) qs.set("window_hours", params.window_hours);
    if (params.limit) qs.set("limit", params.limit);
    const q = qs.toString();
    return q ? req(`/identity/revisions?${q}`) : req("/identity/revisions");
  },

  // ── Live view WebSocket ───────────────────────────────────────────────────
  openLiveSocket(onMessage) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const key = getApiKey();
    const url = `${proto}//${window.location.host}/ws/cts`;
    // Pass API key via Sec-WebSocket-Protocol header (avoids query-param logging).
    const ws = new WebSocket(url, key ? [key] : undefined);
    ws.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data));
      } catch (err) {
        console.error("cts_live_ws_parse_error", err);
      }
    };
    return ws;
  },

  // ── Bbox annotations ──────────────────────────────────────────────────────
  getKeyframeBboxes: (keyframeId) =>
    req(`/identity/keyframes/${encodeURIComponent(keyframeId)}/bboxes`),
  overrideBbox: (annotationId, bbox) =>
    req(`/identity/bboxes/${encodeURIComponent(annotationId)}/override`, {
      method: "PUT",
      body: JSON.stringify(bbox),
    }),
  deleteBbox: (annotationId) =>
    req(`/identity/bboxes/${encodeURIComponent(annotationId)}`, {
      method: "DELETE",
    }),
  // Batch bbox operations
  applyBboxBatch: (keyframeId, operations) =>
    req("/identity/bboxes/batch", {
      method: "POST",
      body: JSON.stringify({ keyframe_id: keyframeId, operations }),
    }),
  applyBboxCorrection: (annotationId, identityId, reason) =>
    req("/identity/corrections", {
      method: "POST",
      body: JSON.stringify({
        ph_id: "",
        annotation_id: annotationId,
        new_identity_id: identityId,
        reason: reason || "manual_bbox_tag",
      }),
    }),

  // ── Presence (Block 9) ────────────────────────────────────────────────────
  /**
   * Fetch the fused presence snapshot for one person.
   * @param {string} personId
   * @returns {Promise<{
   *   person_id: string,
   *   status: "present_room"|"present_home"|"asleep"|"away"|"stale"|"unknown",
   *   room_id: string|null,
   *   room_name: string|null,
   *   confidence: number,
   *   last_seen_at: string|null,
   *   dwell_minutes: number|null,
   *   sources: Array<{name: string, confidence: number}>,
   *   inferred_at: string,
   *   notes: string|null,
   * }>}
   * Endpoint: GET /api/v1/cts/presence/{personId}
   * Throws on non-2xx with `error.message` set from the JSON body.
   */
  getPresence(personId) {
    return req(`/presence/${encodeURIComponent(personId)}`);
  },

  /**
   * Read the in-memory presence fuser config (sanitized).
   * Endpoint: GET /api/v1/cts/presence-config
   */
  getPresenceConfig() {
    return req("/presence-config");
  },

  /**
   * Reload presence.yaml from disk into the running fuser.
   * Endpoint: POST /api/v1/cts/presence-config/reload
   */
  reloadPresenceConfig() {
    return req("/presence-config/reload", { method: "POST" });
  },

  // ── Presence timeline ───────────────────────────────────────────────────────
  getPresenceTimeline(personId, params = {}) {
    const qs = new URLSearchParams();
    if (params.since) qs.set("since", params.since);
    if (params.until) qs.set("until", params.until);
    const q = qs.toString();
    return req(`/presence/timeline/${encodeURIComponent(personId)}${q ? "?" + q : ""}`);
  },
  getPresenceDwells(personId, params = {}) {
    const qs = new URLSearchParams();
    if (params.since) qs.set("since", params.since);
    if (params.until) qs.set("until", params.until);
    const q = qs.toString();
    return req(`/presence/dwells/${encodeURIComponent(personId)}${q ? "?" + q : ""}`);
  },
  getCurrentlyIn() {
    return req("/presence/currently_in");
  },

  // ── Gait mobility trend ─────────────────────────────────────────────────────
  getGaitTrend(personId, days = 56) {
    const qs = new URLSearchParams({ person_id: personId, days: String(days) });
    return req(`/gait/trend?${qs}`);
  },
};
