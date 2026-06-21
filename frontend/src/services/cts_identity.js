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
