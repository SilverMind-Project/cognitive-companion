/**
 * The visitor cluster review composable.
 *
 * Owns the review-queue lifecycle for `VisitorsView`: list load, the selection, and the
 * mutations (name a new person; attribute to an existing member or dismiss, for one cluster or
 * many through one batch call; merge exactly two), and the 409-triggered disabled-state explanation's contract: `GET
 * /clusters` returns an empty list when clustering is disabled, `POST` mutations 409; there
 * is no dedicated "disabled" flag on the list envelope, so the disabled banner only appears
 * once a mutation attempt actually 409s).
 *
 * Returns `{ state, actions }` per engineering-standards Section 17.
 */

import { reactive } from "vue";
import { ApiError } from "@/services/http";
import { REVIEW_ERROR_LABELS } from "@/constants/identityReview";
import { useIdentityTargetsStore } from "@/stores/identityTargets";
import {
  getVisitorCluster,
  listVisitorClusters,
  mergeVisitorClusters,
  nameVisitorCluster,
  reviewVisitorClusters,
} from "@/services/modules/visitors";

export function useVisitorReview(notify) {
  const targets = useIdentityTargetsStore();
  const state = reactive({
    clusters: [],
    total: 0,
    listLoading: false,
    listError: "",
    statusFilter: "surfaced",
    disabled: false,
    detail: null,
    detailLoading: false,
    detailError: "",
    acting: false,
    selection: [],
  });

  async function loadList() {
    state.listLoading = true;
    state.listError = "";
    try {
      const data = await listVisitorClusters(state.statusFilter);
      state.clusters = data?.clusters ?? [];
      state.total = data?.total ?? 0;
      return state.clusters;
    } catch (err) {
      state.listError = err.message || String(err);
      throw err;
    } finally {
      state.listLoading = false;
    }
  }

  function setStatusFilter(status) {
    state.statusFilter = status;
    return loadList();
  }

  async function openDetail(clusterId) {
    state.detailLoading = true;
    state.detailError = "";
    try {
      state.detail = await getVisitorCluster(clusterId);
      return state.detail;
    } catch (err) {
      state.detailError = err.message || String(err);
      throw err;
    } finally {
      state.detailLoading = false;
    }
  }

  function closeDetail() {
    state.detail = null;
    state.detailError = "";
  }

  /** One invalidation path: refresh the queue and the open detail, if any. */
  async function invalidate() {
    await loadList();
    if (state.detail?.cluster?.cluster_id) {
      await openDetail(state.detail.cluster.cluster_id).catch(() => {});
    }
  }

  async function _runAction(label, fn) {
    state.acting = true;
    try {
      const result = await fn();
      state.disabled = false;
      if (notify) notify.success(label);
      await invalidate();
      return result;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        state.disabled = true;
        if (notify) {
          notify.warning("Visitor clustering is currently disabled.");
        }
      } else if (notify) {
        notify.error(err.message || String(err));
      }
      throw err;
    } finally {
      state.acting = false;
    }
  }

  function nameCluster(clusterId, { personId, name }) {
    return _runAction("Visitor named", () =>
      nameVisitorCluster(clusterId, { person_id: personId, name }),
    ).then((result) => {
      // Naming created a household member: every picker must offer them from now on.
      void targets.load(true);
      return result;
    });
  }

  /**
   * Decide about one or more clusters: `is_member` (with `targetIdentityId`), `not_enrolled`,
   * or `not_usable`. One batch call; the server's effect sentence is the success message, and a
   * cluster that could not be updated is reported by count and reason, not as a failed batch.
   */
  async function review(clusterIds, verdict, targetIdentityId = null) {
    state.acting = true;
    try {
      const result = await reviewVisitorClusters({
        cluster_ids: clusterIds,
        verdict,
        ...(targetIdentityId ? { target_identity_id: targetIdentityId } : {}),
      });
      state.disabled = false;
      if (result.reviewed && notify) notify.success(result.effect);
      if (result.failed && notify) {
        const reasons = [
          ...new Set(
            result.results
              .filter((r) => !r.ok)
              .map((r) => REVIEW_ERROR_LABELS[r.error_code] ?? "could not be updated"),
          ),
        ];
        notify.warning(`${result.failed} not updated: ${reasons.join("; ")}.`);
      }
      state.selection = state.selection.filter(
        (id) => !result.results.some((r) => r.ok && r.id === id),
      );
      await invalidate();
      return result;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        state.disabled = true;
        if (notify) notify.warning("Visitor clustering is currently disabled.");
      } else if (notify) {
        notify.error(err.message || String(err));
      }
      throw err;
    } finally {
      state.acting = false;
    }
  }

  function toggleSelection(clusterId) {
    const next = new Set(state.selection);
    if (next.has(clusterId)) next.delete(clusterId);
    else next.add(clusterId);
    state.selection = Array.from(next);
  }

  function clearSelection() {
    state.selection = [];
  }

  /** Merge needs exactly two selected clusters (the view only enables it then). */
  function mergeSelected() {
    const [a, b] = state.selection;
    return _runAction("Clusters merged", () => mergeVisitorClusters(a, b)).then((result) => {
      clearSelection();
      return result;
    });
  }

  return {
    state,
    actions: {
      loadList,
      setStatusFilter,
      openDetail,
      closeDetail,
      invalidate,
      nameCluster,
      review,
      toggleSelection,
      clearSelection,
      mergeSelected,
    },
  };
}
