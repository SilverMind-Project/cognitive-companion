/**
 * The visitor cluster review composable.
 *
 * Owns the review-queue lifecycle for `VisitorsView`: list load, the naming/dismiss/merge
 * mutations, and the 409-triggered disabled-state explanation's contract: `GET
 * /clusters` returns an empty list when clustering is disabled, `POST` mutations 409; there
 * is no dedicated "disabled" flag on the list envelope, so the disabled banner only appears
 * once a mutation attempt actually 409s).
 *
 * Returns `{ state, actions }` per engineering-standards Section 17.
 */

import { reactive } from "vue";
import { ApiError } from "@/services/http";
import {
  dismissVisitorCluster,
  getVisitorCluster,
  listVisitorClusters,
  mergeVisitorClusters,
  nameVisitorCluster,
} from "@/services/modules/visitors";

export function useVisitorReview(notify) {
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
    mergeSelection: [],
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
    );
  }

  function dismissCluster(clusterId) {
    return _runAction("Cluster dismissed", () => dismissVisitorCluster(clusterId));
  }

  function toggleMergeSelection(clusterId) {
    const next = new Set(state.mergeSelection);
    if (next.has(clusterId)) next.delete(clusterId);
    else next.add(clusterId);
    state.mergeSelection = Array.from(next).slice(-2); // merge is exactly two clusters
  }

  function clearMergeSelection() {
    state.mergeSelection = [];
  }

  function mergeSelected() {
    const [a, b] = state.mergeSelection;
    return _runAction("Clusters merged", () => mergeVisitorClusters(a, b)).then((result) => {
      clearMergeSelection();
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
      dismissCluster,
      toggleMergeSelection,
      clearMergeSelection,
      mergeSelected,
    },
  };
}
