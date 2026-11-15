/**
 * The face calibration review composable.
 *
 * Owns the labeling queue for `FaceCalibrationView`: unlabeled captures one at a time, the
 * household residents an operator can assign (active, non-guest members, in name order so the
 * number keys are stable), the progress summary, and the label/reject/delete mutations. A labeled
 * or rejected capture leaves the queue and the next one becomes current; the next page loads when
 * the queue runs out.
 *
 * Returns `{ state, actions }` per engineering-standards Section 17.
 */

import { computed, reactive } from "vue";
import { appliedIds, batchReviewNotices } from "@/constants/identityReview";
import {
  deleteCalibrationCandidate,
  getFaceCalibrationSummary,
  labelCalibrationCandidate,
  listCalibrationCandidates,
  rejectCalibrationCandidate,
  reviewCalibrationCandidates,
  type CalibrationBatchReview,
  type CalibrationCandidateView,
  type FaceCalibrationSummary,
} from "@/services/modules/face_calibration";
import type { IdentityTarget } from "@/services/modules/identity_targets";
import { useIdentityTargetsStore } from "@/stores/identityTargets";
import { ApiError } from "@/services/http";

interface Notify {
  success: (message: string) => void;
  error: (message: string) => void;
  warning: (message: string) => void;
}

/** Residents reachable by a single number key. */
const MAX_KEYED_RESIDENTS = 9;

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export function useFaceCalibrationReview(notify: Notify) {
  const targets = useIdentityTargetsStore();
  const state = reactive({
    queue: [] as CalibrationCandidateView[],
    nextCursor: null as string | null,
    index: 0,
    residents: [] as IdentityTarget[],
    summary: null as FaceCalibrationSummary | null,
    loading: false,
    error: "",
    // The caller lacks `face_calibration.review`; retrying cannot help, so the view shows no queue.
    forbidden: false,
    acting: false,
    // Select several: the operator picks captures from the loaded queue for one batch decision.
    selecting: false,
    selection: [] as string[],
  });

  const current = computed(() => state.queue[state.index] ?? null);
  const keyedResidents = computed(() => state.residents.slice(0, MAX_KEYED_RESIDENTS));

  async function refreshSummary() {
    state.summary = await getFaceCalibrationSummary();
  }

  async function load() {
    state.loading = true;
    state.error = "";
    state.forbidden = false;
    try {
      const [page] = await Promise.all([
        listCalibrationCandidates("unlabeled"),
        targets.load(true),
        refreshSummary(),
      ]);
      if (targets.error) throw new Error(targets.error);
      state.queue = page?.candidates ?? [];
      state.nextCursor = page?.next_cursor ?? null;
      state.index = 0;
      // The shared list is already active members in name order; residents exclude guests.
      state.residents = targets.targets.filter((t) => !t.is_guest);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) state.forbidden = true;
      else state.error = errorText(err);
    } finally {
      state.loading = false;
    }
  }

  async function loadMoreIfNeeded() {
    if (state.queue.length > 0 || !state.nextCursor) return;
    const page = await listCalibrationCandidates("unlabeled", state.nextCursor);
    state.queue = page?.candidates ?? [];
    state.nextCursor = page?.next_cursor ?? null;
    state.index = 0;
  }

  /** Drop the current capture from the queue, keeping the cursor on the next one. */
  async function _advance() {
    state.queue.splice(state.index, 1);
    if (state.index >= state.queue.length) state.index = Math.max(0, state.queue.length - 1);
    await loadMoreIfNeeded();
  }

  async function _mutate(action: () => Promise<unknown>, failure: string) {
    const candidate = current.value;
    if (!candidate || state.acting) return;
    state.acting = true;
    try {
      await action();
      await _advance();
      await refreshSummary().catch(() => undefined);
    } catch (err) {
      notify.error(`${failure}: ${errorText(err)}`);
    } finally {
      state.acting = false;
    }
  }

  function labelResident(position: number) {
    const resident = keyedResidents.value[position];
    const candidate = current.value;
    if (!resident || !candidate) return Promise.resolve();
    return _mutate(
      () =>
        labelCalibrationCandidate(candidate.candidate_id, {
          label_kind: "member",
          label_identity_id: resident.identity_id,
        }),
      "Could not save the label",
    );
  }

  function labelNotEnrolled() {
    const candidate = current.value;
    if (!candidate) return Promise.resolve();
    return _mutate(
      () => labelCalibrationCandidate(candidate.candidate_id, { label_kind: "not_enrolled" }),
      "Could not save the label",
    );
  }

  function labelNotAFace() {
    const candidate = current.value;
    if (!candidate) return Promise.resolve();
    return _mutate(
      () => labelCalibrationCandidate(candidate.candidate_id, { label_kind: "not_a_face" }),
      "Could not save the label",
    );
  }

  function reject() {
    const candidate = current.value;
    if (!candidate) return Promise.resolve();
    return _mutate(
      () => rejectCalibrationCandidate(candidate.candidate_id),
      "Could not reject the capture",
    );
  }

  function remove() {
    const candidate = current.value;
    if (!candidate) return Promise.resolve();
    return _mutate(
      () => deleteCalibrationCandidate(candidate.candidate_id),
      "Could not delete the capture",
    );
  }

  function setSelecting(on: boolean) {
    state.selecting = on;
    state.selection = [];
  }

  function toggleSelection(candidateId: string) {
    state.selection = state.selection.includes(candidateId)
      ? state.selection.filter((id) => id !== candidateId)
      : [...state.selection, candidateId];
  }

  function selectAll() {
    state.selection = state.queue.map((c) => c.candidate_id);
  }

  function clearSelection() {
    state.selection = [];
  }

  /**
   * Label the selected captures in one batch. Only verdicts that name nobody are offered here; a
   * member label is given one face at a time. Applied captures leave the queue; any that could
   * not be updated stay selected and are reported.
   */
  async function reviewSelected(verdict: CalibrationBatchReview["verdict"]) {
    if (!state.selection.length || state.acting) return;
    state.acting = true;
    try {
      const result = await reviewCalibrationCandidates({
        candidate_ids: [...state.selection],
        verdict,
      });
      const notices = batchReviewNotices(result);
      if (notices.success) notify.success(notices.success);
      if (notices.warning) notify.warning(notices.warning);
      const applied = appliedIds(result);
      state.queue = state.queue.filter((c) => !applied.has(c.candidate_id));
      state.selection = state.selection.filter((id) => !applied.has(id));
      state.index = Math.min(state.index, Math.max(0, state.queue.length - 1));
      await loadMoreIfNeeded();
      await refreshSummary().catch(() => undefined);
    } catch (err) {
      notify.error(`Could not save the labels: ${errorText(err)}`);
    } finally {
      state.acting = false;
    }
  }

  function next() {
    if (state.index < state.queue.length - 1) state.index += 1;
  }

  function previous() {
    if (state.index > 0) state.index -= 1;
  }

  return {
    state,
    current,
    keyedResidents,
    actions: {
      load,
      labelResident,
      labelNotEnrolled,
      labelNotAFace,
      reject,
      remove,
      next,
      previous,
      setSelecting,
      toggleSelection,
      selectAll,
      clearSelection,
      reviewSelected,
    },
  };
}
