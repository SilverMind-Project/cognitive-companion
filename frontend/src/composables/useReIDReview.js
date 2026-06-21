/**
 * M09: the ReID review-queue composable.
 *
 * Owns the review queue lifecycle for `CTSReIDReviewView`: paginated/filtered
 * candidate list, selection, the detail drawer, the approve/relabel/reject/
 * batch-reject/compensate mutations, and the shared invalidation that refreshes
 * the queue and the Keyframe/PH pending-review counts after any action.
 *
 * Returns `{ state, actions }` per engineering-standards Section 17. The server
 * owns identity authority, lifecycle state, and eligibility. This composable
 * never derives them: it disables a stale approval when the server says
 * `eligible: false` and surfaces the 409 re-fetch flow rather than retrying.
 *
 * Stale-response protection: every list load carries a monotonic request id, so
 * a slow earlier response can never overwrite a newer one.
 */

import { computed, ref } from "vue";
import { ctsReidReview, ctsIdentity, CorrectionError } from "@/services/cts_identity";

const PAGE_SIZE = 25;

export function useReIDReview(notify) {
  // -- list + pagination + filters -----------------------------------------
  const candidates = ref([]);
  const total = ref(0);
  const limit = ref(PAGE_SIZE);
  const offset = ref(0);
  const listLoading = ref(false);
  const listError = ref("");
  const filters = ref({
    state: "pending_review",
    identity_id: null,
    camera_id: null,
    model_version: null,
    source_type: null,
  });

  // -- selection (batch reject only) ---------------------------------------
  const selected = ref(new Set());

  // -- detail drawer --------------------------------------------------------
  const detail = ref(null);
  const detailLoading = ref(false);
  const detailError = ref("");

  // -- mutations ------------------------------------------------------------
  const acting = ref(false);

  // -- counts (shared indicator source) ------------------------------------
  const counts = ref({ pending_review: 0, operator_verified: 0, rejected: 0 });

  // -- relabel targets (active household roster, not gallery identities) ----
  const targets = ref([]);
  const targetsLoading = ref(false);

  let _listSeq = 0;

  const page = computed(() => Math.floor(offset.value / limit.value) + 1);
  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / limit.value)));
  const selectedIds = computed(() => Array.from(selected.value));

  async function loadList() {
    const seq = ++_listSeq;
    listLoading.value = true;
    listError.value = "";
    try {
      const data = await ctsReidReview.list({
        ...filters.value,
        limit: limit.value,
        offset: offset.value,
      });
      // Drop a stale response that a newer request has superseded.
      if (seq !== _listSeq) return candidates.value;
      candidates.value = data?.candidates || [];
      total.value = data?.total || 0;
      // Drop selections no longer on the page.
      const present = new Set(candidates.value.map((c) => c.candidate_id));
      selected.value = new Set([...selected.value].filter((id) => present.has(id)));
      return candidates.value;
    } catch (err) {
      if (seq === _listSeq) listError.value = err.message || String(err);
      throw err;
    } finally {
      if (seq === _listSeq) listLoading.value = false;
    }
  }

  async function loadCounts() {
    try {
      counts.value = await ctsReidReview.counts();
      return counts.value;
    } catch {
      // Counts are decoration; a failure must not block the queue.
      return counts.value;
    }
  }

  /** Load the active household roster used as relabel targets. Independent of
   *  gallery population: relabel assigns a household member, never a gallery id. */
  async function loadTargets() {
    targetsLoading.value = true;
    try {
      const data = await ctsIdentity.correctionTargets();
      targets.value = data?.targets || [];
      return targets.value;
    } catch {
      return targets.value;
    } finally {
      targetsLoading.value = false;
    }
  }

  /** One invalidation path: refresh queue, counts, and the open detail. */
  async function invalidate() {
    await Promise.all([loadList(), loadCounts()]);
    if (detail.value?.candidate?.candidate_id) {
      await openDetail(detail.value.candidate.candidate_id).catch(() => {});
    }
  }

  function setFilter(key, value) {
    filters.value = { ...filters.value, [key]: value };
    offset.value = 0; // Any filter change resets to the first page.
    return loadList();
  }

  function goToPage(p) {
    const clamped = Math.min(Math.max(1, p), pageCount.value);
    offset.value = (clamped - 1) * limit.value;
    return loadList();
  }

  async function openDetail(candidateId) {
    detailLoading.value = true;
    detailError.value = "";
    try {
      detail.value = await ctsReidReview.detail(candidateId);
      return detail.value;
    } catch (err) {
      detailError.value = err.message || String(err);
      throw err;
    } finally {
      detailLoading.value = false;
    }
  }

  function closeDetail() {
    detail.value = null;
    detailError.value = "";
  }

  function toggleSelected(candidateId) {
    const next = new Set(selected.value);
    if (next.has(candidateId)) next.delete(candidateId);
    else next.add(candidateId);
    selected.value = next;
  }

  function clearSelection() {
    selected.value = new Set();
  }

  function _baseVersion(candidateId) {
    const row =
      candidates.value.find((c) => c.candidate_id === candidateId) ||
      (detail.value?.candidate?.candidate_id === candidateId
        ? detail.value.candidate
        : null);
    return row?.audit_version;
  }

  async function _runAction(label, fn) {
    acting.value = true;
    try {
      const result = await fn();
      if (notify) notify.success(label);
      await invalidate();
      return result;
    } catch (err) {
      // A 409 means the candidate moved or became ineligible: re-fetch so the
      // operator sees current state rather than acting on stale data.
      if (err instanceof CorrectionError && err.status === 409) {
        if (notify) {
          notify.warning("This candidate changed since you loaded it. Review the refreshed state.");
        }
        await invalidate().catch(() => {});
      } else if (notify) {
        notify.error(err.message || String(err));
      }
      throw err;
    } finally {
      acting.value = false;
    }
  }

  function approve(candidateId, { note = null } = {}) {
    return _runAction("Candidate verified", () =>
      ctsReidReview.approve(candidateId, {
        base_audit_version: _baseVersion(candidateId),
        note,
      }),
    );
  }

  function relabel(candidateId, { target_identity_id, note = null }) {
    return _runAction("Candidate relabeled and verified", () =>
      ctsReidReview.relabel(candidateId, {
        base_audit_version: _baseVersion(candidateId),
        target_identity_id,
        note,
      }),
    );
  }

  function reject(candidateId, { reason, note = null }) {
    return _runAction("Candidate rejected", () =>
      ctsReidReview.reject(candidateId, {
        base_audit_version: _baseVersion(candidateId),
        reason,
        note,
      }),
    );
  }

  function rejectSelected({ reason, note = null }) {
    const items = selectedIds.value.map((id) => ({
      candidate_id: id,
      base_audit_version: _baseVersion(id),
    }));
    return _runAction("Selected candidates rejected", async () => {
      const result = await ctsReidReview.rejectBatch({ reason, note, items });
      clearSelection();
      return result;
    });
  }

  function compensate(candidateId) {
    return _runAction("Approval undone", () => ctsReidReview.compensate(candidateId));
  }

  return {
    state: {
      candidates,
      total,
      limit,
      offset,
      page,
      pageCount,
      listLoading,
      listError,
      filters,
      selected,
      selectedIds,
      detail,
      detailLoading,
      detailError,
      acting,
      counts,
      targets,
      targetsLoading,
    },
    actions: {
      loadList,
      loadCounts,
      loadTargets,
      invalidate,
      setFilter,
      goToPage,
      openDetail,
      closeDetail,
      toggleSelected,
      clearSelection,
      approve,
      relabel,
      reject,
      rejectSelected,
      compensate,
    },
  };
}
