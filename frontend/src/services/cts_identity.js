/**
 * M08: shared identity-correction BFF client.
 *
 * One service module for the correction workflow used by BOTH the Keyframes
 * surface and the PH inspector: correction targets, segment proposals, apply,
 * compensate, and projection-job status.
 *
 * Errors carry the upstream HTTP `status` and domain `code` so the composable
 * can branch precisely -- a 409 `correction.stale_version` triggers a re-propose
 * and forced reconfirmation rather than a generic toast.
 */

import { ApiError, requestJson } from "./http";

const BASE = "/api/v1/cts";

export class CorrectionError extends Error {
  constructor(message, { status = 0, code = "" } = {}) {
    super(message);
    this.name = "CorrectionError";
    this.status = status;
    this.code = code;
  }

  /** True for an optimistic-lock conflict (proposal must be refreshed). */
  get isStale() {
    return this.status === 409 && this.code === "correction.stale_version";
  }
}

/**
 * Translate the shared core's ApiError into this domain's CorrectionError.
 *
 * The domain `code` lives inside the envelope's object `detail`, and callers branch on it
 * (`isStale` drives re-propose + forced reconfirmation), so it has to survive. ApiError already
 * renders the same message this module used to build by hand, so only status/code are lifted.
 */
function toCorrectionError(err) {
  if (err instanceof ApiError) {
    const { detail } = err;
    const code = detail && typeof detail === "object" ? detail.code || "" : "";
    return new CorrectionError(err.message, { status: err.status, code });
  }
  // Transport failure: requestJson already prefixed it with "Network error:".
  return new CorrectionError(err?.message || "Network error");
}

async function req(path, options = {}) {
  try {
    return await requestJson(`${BASE}${path}`, options);
  } catch (err) {
    throw toCorrectionError(err);
  }
}

export const ctsIdentity = {
  /** Active household roster -- the authoritative correction targets. */
  correctionTargets: () => req("/identity/correction-targets"),

  /** Advisory observation-bounded segment proposal. */
  propose: ({ ph_id, observation_id = null, at = null } = {}) =>
    req("/identity/corrections/propose", {
      method: "POST",
      body: JSON.stringify({ ph_id, observation_id, at }),
    }),

  /** Apply an explicit frame-only/bounded correction or Set-to-Unknown.
   *  `actor` is injected server-side; never send it from the browser. */
  apply: (payload) =>
    req("/identity/corrections/apply", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Undo a correction via a compensating revision. */
  compensate: (correctionId) =>
    req(`/identity/corrections/${encodeURIComponent(correctionId)}/compensate`, {
      method: "POST",
      body: JSON.stringify({}),
    }),

  /** Projection-job status for a revision; polled until terminal. */
  job: (revisionId) => req(`/identity/corrections/jobs/${encodeURIComponent(revisionId)}`, {}),
};

/**
 * M09: ReID gallery review-queue client.
 *
 * A separate biometric-admin surface behind the `cts.identity.gallery_review`
 * permission. The same `CorrectionError` carries the upstream `status`/`code`,
 * so the composable can disable a stale approval on a 409 rather than retry it.
 * `actor` is always injected server-side; never send it from the browser.
 */
export const ctsReidReview = {
  /** Paginated review candidates with filters. `query` is a plain object. */
  list: (query = {}) => {
    const params = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => {
      if (v !== null && v !== undefined && v !== "") params.set(k, v);
    });
    const qs = params.toString();
    return req(`/identity/reid-review/candidates${qs ? `?${qs}` : ""}`, {});
  },

  /** Candidate detail: provenance, review history, and server eligibility. */
  detail: (candidateId) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}`, {}),

  /** Review history for one candidate. */
  events: (candidateId) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/events`, {}),

  /** Queue counts used by Keyframe/PH indicators. */
  counts: () => req("/identity/reid-review/counts"),

  /** Approve one candidate (individual only). 409 when stale/ineligible. */
  approve: (candidateId, { base_audit_version, note = null }) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ base_audit_version, note }),
    }),

  /** Relabel one candidate to a household target (individual only). */
  relabel: (candidateId, { base_audit_version, target_identity_id, note = null }) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/relabel`, {
      method: "POST",
      body: JSON.stringify({ base_audit_version, target_identity_id, note }),
    }),

  /** Reject one candidate with a structured reason. */
  reject: (candidateId, { base_audit_version, reason, note = null }) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/reject`, {
      method: "POST",
      body: JSON.stringify({ base_audit_version, reason, note }),
    }),

  /** Batch rejection (the only batch action; bulk approval does not exist). */
  rejectBatch: ({ reason, note = null, items }) =>
    req("/identity/reid-review/reject-batch", {
      method: "POST",
      body: JSON.stringify({ reason, note, items }),
    }),

  /** Compensating action: un-verify an approved candidate from its history. */
  compensate: (candidateId) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/compensate`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
