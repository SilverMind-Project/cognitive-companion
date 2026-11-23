import { reactive } from "vue";
import {
  getInfoCardDeliveries,
  getQuizSession,
  getQuizSessions,
  getSeniorKnowledgeQueries,
} from "@/services/modules/interactions";
import { getTagAnalytics } from "@/services/modules/knowledge";
import { requireNotify } from "@/composables/useNotify.js";

/**
 * State + actions for the Knowledge Interactions review page: what the senior asked,
 * which quizzes they took (and how they answered), and which cards they were shown,
 * plus per-tag analytics.
 *
 * Each list is paginated by the server ({items, total}, limit/offset). The page used to
 * load one default page into a client-side table, so anything past it never showed.
 * Date filters are household calendar days (date_from/date_to, inclusive).
 */
export function useKnowledgeInteractions({ notify } = {}) {
  requireNotify("useKnowledgeInteractions", notify);

  function pagedList(fetcher, label) {
    return {
      fetcher,
      label,
      state: reactive({
        items: [],
        total: 0,
        loading: false,
        page: 1,
        itemsPerPage: 15,
        dateFrom: "",
        dateTo: "",
      }),
    };
  }

  const lists = {
    queries: pagedList(getSeniorKnowledgeQueries, "questions"),
    sessions: pagedList(getQuizSessions, "quiz sessions"),
    deliveries: pagedList(getInfoCardDeliveries, "card deliveries"),
  };

  const state = reactive({
    queries: lists.queries.state,
    sessions: lists.sessions.state,
    deliveries: lists.deliveries.state,
    // session id -> detail with responses, loaded when a row is expanded.
    sessionDetails: {},
    loadingSessionId: null,
    analytics: { tags: [], loading: false, error: null },
  });

  async function load(name) {
    const { fetcher, label, state: list } = lists[name];
    list.loading = true;
    try {
      const params = {
        limit: list.itemsPerPage,
        offset: (list.page - 1) * list.itemsPerPage,
      };
      if (list.dateFrom) params.date_from = list.dateFrom;
      if (list.dateTo) params.date_to = list.dateTo;
      const res = await fetcher(params);
      list.items = res?.items ?? [];
      list.total = res?.total ?? 0;
    } catch (err) {
      notify.error(`Failed to load ${label}: ` + (err.message || err));
    } finally {
      list.loading = false;
    }
  }

  /** v-data-table-server @update:options. */
  function onOptions(name, { page, itemsPerPage }) {
    const list = lists[name].state;
    if (page === list.page && itemsPerPage === list.itemsPerPage) return;
    if (itemsPerPage !== list.itemsPerPage) {
      list.itemsPerPage = itemsPerPage;
      list.page = 1;
    } else {
      list.page = page;
    }
    load(name);
  }

  /** A changed date range starts again from page 1. */
  function applyDates(name) {
    lists[name].state.page = 1;
    load(name);
  }

  async function loadSessionDetail(sessionId) {
    if (state.sessionDetails[sessionId]) return;
    state.loadingSessionId = sessionId;
    try {
      const detail = await getQuizSession(sessionId);
      state.sessionDetails = { ...state.sessionDetails, [sessionId]: detail };
    } catch (err) {
      notify.error("Failed to load the quiz session: " + (err.message || err));
    } finally {
      state.loadingSessionId = null;
    }
  }

  async function loadTagAnalytics() {
    state.analytics.loading = true;
    state.analytics.error = null;
    try {
      state.analytics.tags = (await getTagAnalytics())?.tags ?? [];
    } catch (err) {
      state.analytics.error = err.message || String(err);
    } finally {
      state.analytics.loading = false;
    }
  }

  return {
    state,
    actions: { load, onOptions, applyDates, loadSessionDetail, loadTagAnalytics },
  };
}
