/**
 * Audit and exemplar grid for wearable-attested faces (the "Attested faces" mode of
 * `FaceCalibrationView`).
 *
 * A wearable association labeled these faces automatically. The operator judges a uniform random
 * sample the server draws (never a sample of their choosing), which decides whether the labels
 * may ever be used for calibration, and may promote a good face into recognition one at a time.
 * The server decides the audit bar and promotion eligibility; this composable only shows them.
 *
 * Returns `{ state, actions }` per engineering-standards Section 17.
 */

import { computed, reactive } from "vue";
import {
  auditAttestedFace,
  getAttestedFaceAuditSample,
  getAttestedFaceAuditSummary,
  listAttestedFaces,
  promoteCalibrationCandidate,
  type AttestationAuditSummary,
  type AttestationAuditVerdict,
  type CalibrationCandidateView,
} from "@/services/modules/face_calibration";
import { ApiError } from "@/services/http";
import { requireNotify } from "@/composables/useNotify.js";

/** The view's notifier from `useNotify()`: callable, with per-severity helpers. */
interface Notify {
  (message: string, color?: string): void;
  success: (message: string) => void;
  error: (message: string) => void;
}

const SAMPLE_SIZE = 25;
const GRID_LIMIT = 60;

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function useAttestedFaceAudit(notify: Notify) {
  requireNotify("useAttestedFaceAudit", notify);
  const state = reactive({
    sample: [] as CalibrationCandidateView[],
    index: 0,
    exemplars: [] as CalibrationCandidateView[],
    summary: null as AttestationAuditSummary | null,
    loading: false,
    error: "",
    forbidden: false,
    acting: false,
  });

  const current = computed(() => state.sample[state.index] ?? null);

  async function load() {
    state.loading = true;
    state.error = "";
    state.forbidden = false;
    try {
      const [sample, summary, grid] = await Promise.all([
        getAttestedFaceAuditSample(SAMPLE_SIZE),
        getAttestedFaceAuditSummary(),
        listAttestedFaces(),
      ]);
      state.sample = sample.candidates;
      state.index = 0;
      state.summary = summary;
      state.exemplars = grid.candidates
        .filter((c) => c.audit_verdict !== "wrong" && c.audit_verdict !== "not_a_face")
        .slice(0, GRID_LIMIT);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) state.forbidden = true;
      else state.error = `Could not load attested faces: ${errorText(err)}`;
    } finally {
      state.loading = false;
    }
  }

  async function audit(verdict: AttestationAuditVerdict) {
    const face = current.value;
    if (!face || state.acting) return;
    state.acting = true;
    try {
      await auditAttestedFace(face.candidate_id, verdict);
      state.sample.splice(state.index, 1);
      if (state.index >= state.sample.length) state.index = Math.max(0, state.sample.length - 1);
      state.summary = await getAttestedFaceAuditSummary();
    } catch (err) {
      notify.error(`Could not record the audit: ${errorText(err)}`);
    } finally {
      state.acting = false;
    }
  }

  async function promote(candidateId: string) {
    state.acting = true;
    try {
      const result = await promoteCalibrationCandidate(candidateId);
      state.exemplars = state.exemplars.map((c) =>
        c.candidate_id === candidateId ? { ...c, promoted: true, promotion_eligible: false } : c,
      );
      notify.success(`Added a ${result.pose_bin} face to the recognition gallery.`);
    } catch (err) {
      notify.error(`Could not use this face for recognition: ${errorText(err)}`);
    } finally {
      state.acting = false;
    }
  }

  function next() {
    if (state.index < state.sample.length - 1) state.index += 1;
  }

  function previous() {
    if (state.index > 0) state.index -= 1;
  }

  return { state, current, actions: { load, audit, promote, next, previous } };
}
