/**
 * CTS (Continuous Tracking System) API client.
 *
 * All calls go through the CC backend BFF — the browser never contacts the
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
};
