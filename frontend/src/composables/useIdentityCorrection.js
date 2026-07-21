/**
 * the one identity-correction composable.
 *
 * Shared by the Keyframes surface and the PH inspector. Owns correction
 * targets, the segment proposal + optimistic version token, apply (frame-only,
 * bounded, or explicit Set-to-Unknown), compensation, and projection-job
 * polling. Returns `{ state, actions }` per engineering-standards Section 17.
 *
 * The server owns all identity authority, boundaries, confidence, eligibility,
 * and job status. This composable never derives them; it only orchestrates the
 * request lifecycle and surfaces server state, including the stale-version
 * (HTTP 409) re-propose-and-reconfirm flow.
 */

import { ref } from "vue";
import { ctsIdentity, CorrectionError } from "@/services/cts_identity";

const TERMINAL = new Set(["completed", "failed"]);

export function useIdentityCorrection(notify) {
  // -- correction targets (active household roster) -------------------------
  const targets = ref([]);
  const targetsLoading = ref(false);
  const targetsError = ref("");
  const galleryAvailable = ref(true);

  // -- proposal + version token --------------------------------------------
  const proposal = ref(null);
  const proposalLoading = ref(false);
  const proposalError = ref("");

  // -- apply / job ----------------------------------------------------------
  const applying = ref(false);
  const staleConflict = ref(false);
  const job = ref(null);
  const jobPolling = ref(false);

  async function loadTargets() {
    targetsLoading.value = true;
    targetsError.value = "";
    try {
      const data = await ctsIdentity.correctionTargets();
      targets.value = data?.targets || [];
      galleryAvailable.value = data?.gallery_available !== false;
      return targets.value;
    } catch (err) {
      targetsError.value = err.message || String(err);
      throw err;
    } finally {
      targetsLoading.value = false;
    }
  }

  async function propose({ ph_id, observation_id = null, at = null } = {}) {
    proposalLoading.value = true;
    proposalError.value = "";
    try {
      const data = await ctsIdentity.propose({ ph_id, observation_id, at });
      proposal.value = data;
      return data;
    } catch (err) {
      proposalError.value = err.message || String(err);
      throw err;
    } finally {
      proposalLoading.value = false;
    }
  }

  /**
   * Apply a correction. The caller assembles the explicit payload (scope,
   * range, target/unknown, reason). On a stale version (409) the proposal is
   * refreshed, `staleConflict` is set, and the error is re-thrown so the UI can
   * highlight the changed range and force reconfirmation -- the correction is
   * NOT silently retried.
   */
  async function apply(payload) {
    applying.value = true;
    staleConflict.value = false;
    job.value = null;
    try {
      const result = await ctsIdentity.apply(payload);
      job.value = {
        revision_id: result.revision_id,
        status: result.job_status,
        required_projections: [],
        row_counts: {},
        attempts: 0,
        last_error: null,
      };
      if (notify) notify.success("Correction submitted");
      return result;
    } catch (err) {
      if (err instanceof CorrectionError && err.isStale) {
        staleConflict.value = true;
        if (payload?.ph_id) {
          // Re-fetch the proposal so the operator reviews the changed range.
          await propose({ ph_id: payload.ph_id }).catch(() => {});
        }
        if (notify) {
          notify.warning(
            "The track changed since you started. Review the updated range and confirm again.",
          );
        }
      } else if (notify) {
        notify.error(err.message || String(err));
      }
      throw err;
    } finally {
      applying.value = false;
    }
  }

  async function compensate(correctionId) {
    try {
      const result = await ctsIdentity.compensate(correctionId);
      if (notify) notify.success("Correction undone");
      return result;
    } catch (err) {
      if (notify) notify.error(err.message || String(err));
      throw err;
    }
  }

  /** Fetch the latest job state once. */
  async function refreshJob(revisionId) {
    const data = await ctsIdentity.job(revisionId);
    job.value = data;
    return data;
  }

  /**
   * Poll the projection job until it reaches a terminal state. Resolves with
   * the terminal job. `intervalMs`/`maxAttempts` are injectable for tests.
   */
  async function pollJob(revisionId, { intervalMs = 1500, maxAttempts = 40 } = {}) {
    jobPolling.value = true;
    try {
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        const data = await refreshJob(revisionId);
        if (TERMINAL.has(data.status)) return data;
        if (attempt < maxAttempts - 1 && intervalMs > 0) {
          await new Promise((r) => setTimeout(r, intervalMs));
        }
      }
      return job.value;
    } finally {
      jobPolling.value = false;
    }
  }

  function reset() {
    proposal.value = null;
    proposalError.value = "";
    staleConflict.value = false;
    job.value = null;
  }

  return {
    state: {
      targets,
      targetsLoading,
      targetsError,
      galleryAvailable,
      proposal,
      proposalLoading,
      proposalError,
      applying,
      staleConflict,
      job,
      jobPolling,
    },
    actions: { loadTargets, propose, apply, compensate, refreshJob, pollJob, reset },
  };
}
