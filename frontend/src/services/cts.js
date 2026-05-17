/**
 * CTS (Continuous Tracking System) API client.
 *
 * All calls go through the CC backend BFF: the browser never contacts the
 * tracking microservices directly.
 */

const BASE = "/api/v1/cts";

function getApiKey() {
  return localStorage.getItem("cc_api_key") || "";
}

function authHeaders(extra = {}) {
  const key = getApiKey();
  return { ...(key ? { "X-API-Key": key } : {}), ...extra };
}

async function req(path, options = {}) {
  const headers = authHeaders({
    "Content-Type": "application/json",
    ...options.headers,
  });
  const resp = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    const detail = body.detail;
    const msg =
      typeof detail === "object" ? detail.message || JSON.stringify(detail) : detail;
    throw new Error(msg || `HTTP ${resp.status}`);
  }
  if (resp.status === 204) return null;
  return resp.json();
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
  getSnapshot: async (id) => {
    const key = getApiKey();
    const resp = await fetch(`${BASE}/cameras/${id}/snapshot`, {
      headers: key ? { "X-API-Key": key } : {},
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return URL.createObjectURL(await resp.blob());
  },
  getCameraHealth: (id) => req(`/cameras/${id}/health`),
  reloadCamera: (id) => req(`/cameras/${id}/reload`, { method: "POST" }),

  // ── Calibration: homography ─────────────────────────────────────────────────
  postHomography: (camera_id, points) =>
    req("/calibration/homography", {
      method: "POST",
      body: JSON.stringify({ camera_id, points }),
    }),
  getHomography: (camera_id) => req(`/calibration/homography/${camera_id}`),

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
  getOverlapGroups: () => req("/overlap_groups"),

  // ── Dementia signals ────────────────────────────────────────────────────────
  getSignals: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.person_id) qs.set("person_id", params.person_id);
    if (params.signal_type) qs.set("signal_type", params.signal_type);
    if (params.severity) qs.set("severity", params.severity);
    if (params.window_hours) qs.set("window_hours", params.window_hours);
    if (params.limit) qs.set("limit", params.limit);
    const q = qs.toString();
    return q ? req(`/signals?${q}`) : req("/signals");
  },
  acknowledgeSignal: (signalId) =>
    req(`/signals/${signalId}/ack`, { method: "POST" }),
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
    const qs = new URLSearchParams();
    if (params.person_id) qs.set("person_id", params.person_id);
    if (params.signal_type) qs.set("signal_type", params.signal_type);
    if (params.after) qs.set("after", params.after);
    if (params.limit) qs.set("limit", params.limit);
    const q = qs.toString();
    return q ? req(`/keyframes?${q}`) : req("/keyframes");
  },
  getKeyframe: (sampleId) => req(`/keyframes/${sampleId}`),
  retainKeyframe: (sampleId) =>
    req(`/keyframes/${sampleId}/retain`, { method: "POST" }),

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

  // ── Gallery enrollment ─────────────────────────────────────────────────────
  enrollFromTracklet: (payload) =>
    req("/gallery/enroll", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ── Identity health + bulk enrollment ─────────────────────────────────────
  getIdentityHealth: () => req("/identity/health"),
  enrollBatch: (items) =>
    req("/identity/enroll/batch", {
      method: "POST",
      body: JSON.stringify({ items }),
    }),

  // ── Identity corrections (M9) ──────────────────────────────────────────────
  getIdentities: () => req("/identity/identities"),
  getGlobalTracks: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.open_only !== undefined) qs.set("open_only", params.open_only);
    if (params.limit) qs.set("limit", params.limit);
    if (params.offset) qs.set("offset", params.offset);
    if (params.camera_id) qs.set("camera_id", params.camera_id);
    if (params.status) qs.set("status", params.status);
    if (params.search) qs.set("search", params.search);
    const q = qs.toString();
    return q ? req(`/identity/global_tracks?${q}`) : req("/identity/global_tracks");
  },
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
  // ── Identity track enrichment (Phase 1C) ──────────────────────────────
  getGlobalTrackDetail: (id) => req(`/identity/global_tracks/${encodeURIComponent(id)}`),
  getCoOccurringTracks: (id) => req(`/identity/global_tracks/${encodeURIComponent(id)}/co_occurring`),
  getTrackKeyframes: (id) => req(`/identity/global_tracks/${encodeURIComponent(id)}/keyframes`),
  getTrackTrail: (id) => req(`/identity/global_tracks/${encodeURIComponent(id)}/trail`),

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
};
