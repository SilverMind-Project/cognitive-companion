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

import { validateContract } from "./contracts.js";

const BASE = "/api/v1/cts";

function getApiKey() {
  return localStorage.getItem("cc_api_key") || "";
}

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

async function req(path, options = {}) {
  const { contract, ...fetchOptions } = options;
  const key = getApiKey();
  const headers = {
    "Content-Type": "application/json",
    ...(key ? { "X-API-Key": key } : {}),
    ...fetchOptions.headers,
  };
  let resp;
  try {
    resp = await fetch(`${BASE}${path}`, { ...fetchOptions, headers });
  } catch (err) {
    throw new CorrectionError(`Network error: ${err.message || "Unable to reach server"}`);
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    const detail = body.detail;
    const code = typeof detail === "object" ? detail.code || "" : "";
    const message =
      typeof detail === "object"
        ? detail.message || JSON.stringify(detail)
        : detail || `HTTP ${resp.status}`;
    throw new CorrectionError(message, { status: resp.status, code });
  }
  if (resp.status === 204) return null;
  const data = await resp.json();
  if (contract) validateContract(contract, data);
  return data;
}

export const ctsIdentity = {
  /** Active household roster -- the authoritative correction targets. */
  correctionTargets: () =>
    req("/identity/correction-targets", { contract: "cts.identity.correctionTargets" }),

  /** Advisory observation-bounded segment proposal. */
  propose: ({ ph_id, observation_id = null, at = null } = {}) =>
    req("/identity/corrections/propose", {
      method: "POST",
      body: JSON.stringify({ ph_id, observation_id, at }),
      contract: "cts.identity.proposal",
    }),

  /** Apply an explicit frame-only/bounded correction or Set-to-Unknown.
   *  `actor` is injected server-side; never send it from the browser. */
  apply: (payload) =>
    req("/identity/corrections/apply", {
      method: "POST",
      body: JSON.stringify(payload),
      contract: "cts.identity.correctionResult",
    }),

  /** Undo a correction via a compensating revision. */
  compensate: (correctionId) =>
    req(`/identity/corrections/${encodeURIComponent(correctionId)}/compensate`, {
      method: "POST",
      body: JSON.stringify({}),
      contract: "cts.identity.correctionResult",
    }),

  /** Projection-job status for a revision; polled until terminal. */
  job: (revisionId) =>
    req(`/identity/corrections/jobs/${encodeURIComponent(revisionId)}`, {
      contract: "cts.identity.correctionJob",
    }),
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
    return req(`/identity/reid-review/candidates${qs ? `?${qs}` : ""}`, {
      contract: "cts.reidReview.list",
    });
  },

  /** Candidate detail: provenance, review history, and server eligibility. */
  detail: (candidateId) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}`, {
      contract: "cts.reidReview.detail",
    }),

  /** Review history for one candidate. */
  events: (candidateId) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/events`, {
      contract: "cts.reidReview.events",
    }),

  /** Queue counts used by Keyframe/PH indicators. */
  counts: () =>
    req("/identity/reid-review/counts", { contract: "cts.reidReview.counts" }),

  /** Approve one candidate (individual only). 409 when stale/ineligible. */
  approve: (candidateId, { base_audit_version, note = null }) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ base_audit_version, note }),
      contract: "cts.reidReview.candidate",
    }),

  /** Relabel one candidate to a household target (individual only). */
  relabel: (candidateId, { base_audit_version, target_identity_id, note = null }) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/relabel`, {
      method: "POST",
      body: JSON.stringify({ base_audit_version, target_identity_id, note }),
      contract: "cts.reidReview.candidate",
    }),

  /** Reject one candidate with a structured reason. */
  reject: (candidateId, { base_audit_version, reason, note = null }) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/reject`, {
      method: "POST",
      body: JSON.stringify({ base_audit_version, reason, note }),
      contract: "cts.reidReview.candidate",
    }),

  /** Batch rejection (the only batch action; bulk approval does not exist). */
  rejectBatch: ({ reason, note = null, items }) =>
    req("/identity/reid-review/reject-batch", {
      method: "POST",
      body: JSON.stringify({ reason, note, items }),
      contract: "cts.reidReview.batchResult",
    }),

  /** Compensating action: un-verify an approved candidate from its history. */
  compensate: (candidateId) =>
    req(`/identity/reid-review/candidates/${encodeURIComponent(candidateId)}/compensate`, {
      method: "POST",
      body: JSON.stringify({}),
      contract: "cts.reidReview.candidate",
    }),
};
