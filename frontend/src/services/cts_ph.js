/**
 * N2: Person Hypothesis API client.
 *
 * Thin wrapper over the CC BFF /cts/ph endpoints. All calls return
 * parsed JSON; errors throw with the server's detail message.
 */

import { ApiError, requestJson } from "./http";

const BASE = "/api/v1/cts";

/**
 * Requests go through the shared core in `http.ts`; only the error *message* format is local.
 *
 * This surface renders "code: message" (e.g. "ph.not_found: No such hypothesis") rather than
 * the message alone, and the PH inspector shows that string directly, so the format is kept
 * rather than flattened to the core's default.
 */
async function req(path, options = {}) {
  try {
    return await requestJson(`${BASE}${path}`, options);
  } catch (err) {
    if (err instanceof ApiError) {
      const detail = err.detail;
      if (detail && typeof detail === "object") {
        const msg =
          [detail.code, detail.message].filter(Boolean).join(": ") || JSON.stringify(detail);
        throw new Error(msg);
      }
      throw new Error(err.message);
    }
    throw err;
  }
}

export const ctsPh = {
  // ── Read ─────────────────────────────────────────────────────────────
  list: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.since) qs.set("since", params.since);
    if (params.until) qs.set("until", params.until);
    if (params.room_id) qs.set("room_id", params.room_id);
    if (params.identity_id) qs.set("identity_id", params.identity_id);
    if (params.state) qs.set("state", params.state);
    if (params.include_transient) qs.set("include_transient", "true");
    if (params.min_duration_s != null) qs.set("min_duration_s", String(params.min_duration_s));
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

  batchMerge: ({ source_ph_ids = [], target_ph_id, reason = "manual_bulk_merge" } = {}) =>
    req("/ph/batch_merge", {
      method: "POST",
      body: JSON.stringify({ source_ph_ids, target_ph_id, reason }),
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

  batchDelete: (phIds = [], reason = "manual_delete") =>
    req("/ph/batch_delete", {
      method: "POST",
      body: JSON.stringify({ ph_ids: phIds, reason }),
    }),

  purgeUnknown: ({ older_than_days, limit = 1000 } = {}) =>
    req("/ph/purge_unknown", {
      method: "POST",
      body: JSON.stringify({ older_than_days, limit }),
    }),
};
