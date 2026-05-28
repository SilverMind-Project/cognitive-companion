/**
 * N2: Person Hypothesis API client.
 *
 * Thin wrapper over the CC BFF /cts/ph endpoints. All calls return
 * parsed JSON; errors throw with the server's detail message.
 */

const BASE = "/api/v1/cts";

async function req(path, options = {}) {
  const apiKey = localStorage.getItem("cc_api_key") || "";
  const headers = {
    "Content-Type": "application/json",
    ...(apiKey ? { "X-API-Key": apiKey } : {}),
    ...options.headers,
  };
  let resp;
  try {
    resp = await fetch(`${BASE}${path}`, { ...options, headers });
  } catch (err) {
    throw new Error(`Network error: ${err.message || "Unable to reach server"}`);
  }
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

export const ctsPh = {
  // ── Read ─────────────────────────────────────────────────────────────
  list: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.since) qs.set("since", params.since);
    if (params.room_id) qs.set("room_id", params.room_id);
    if (params.identity_id) qs.set("identity_id", params.identity_id);
    qs.set("limit", String(params.limit ?? 50));
    qs.set("offset", String(params.offset ?? 0));
    return req(`/ph?${qs}`);
  },

  get: (phId) => req(`/ph/${encodeURIComponent(phId)}`),

  observations: (phId, limit = 200) =>
    req(`/ph/${encodeURIComponent(phId)}/observations?limit=${limit}`),

  keyframes: (phId, limit = 24) =>
    req(`/ph/${encodeURIComponent(phId)}/keyframes?limit=${limit}`),

  trail: (phId, since) => {
    const qs = new URLSearchParams();
    if (since) qs.set("since", since);
    return req(`/ph/${encodeURIComponent(phId)}/trail?${qs}`);
  },

  coPresent: (phId, radiusM = 5) =>
    req(`/ph/${encodeURIComponent(phId)}/co_present?radius_m=${radiusM}`),

  revisions: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.ph_id) qs.set("ph_id", params.ph_id);
    if (params.kind) qs.set("kind", params.kind);
    qs.set("limit", String(params.limit ?? 50));
    if (params.before_id) qs.set("before_id", params.before_id);
    return req(`/ph/revisions?${qs}`);
  },

  // ── Mutations ────────────────────────────────────────────────────────
  correct: (phId, { new_identity_id, reason = "manual" } = {}) =>
    req(`/ph/${encodeURIComponent(phId)}/correct`, {
      method: "POST",
      body: JSON.stringify({ new_identity_id, reason }),
    }),

  merge: ({ source_ph_id, target_ph_id, reason = "manual" } = {}) =>
    req("/ph/merge", {
      method: "POST",
      body: JSON.stringify({ source_ph_id, target_ph_id, reason }),
    }),

  split: (phId, { at_observation_id, reason = "manual" } = {}) =>
    req(`/ph/${encodeURIComponent(phId)}/split`, {
      method: "POST",
      body: JSON.stringify({ at_observation_id, reason }),
    }),

  batchCorrect: (corrections = []) =>
    req("/ph/batch_correct", {
      method: "POST",
      body: JSON.stringify({ corrections }),
    }),
};
