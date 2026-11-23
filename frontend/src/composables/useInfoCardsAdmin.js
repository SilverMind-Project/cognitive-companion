import { reactive } from "vue";
import {
  approveInfoCard,
  archiveInfoCard,
  deleteInfoCard,
  getInfoCards,
  restoreInfoCard,
} from "@/services/modules/info_cards";
import { getKnowledgeDocuments } from "@/services/modules/knowledge";
import { getKnowledgeLayouts } from "@/services/modules/layouts";
import { getLLMModels } from "@/services/modules/pipeline";
import { requireNotify } from "@/composables/useNotify.js";

// The list endpoints cap limit at 200.
const PICKER_LIMIT = 200;
const FILTER_DEBOUNCE_MS = 300;

/**
 * State + actions for the Info Cards admin view: the server-paginated card list, its
 * filters, lifecycle transitions, and the layouts, documents, and models the card dialog
 * picks from.
 */
export function useInfoCardsAdmin({ notify } = {}) {
  requireNotify("useInfoCardsAdmin", notify);

  const state = reactive({
    cards: [],
    totalCards: 0,
    loading: false,
    page: 1,
    itemsPerPage: 20,
    filters: {
      status: null,
      tags: [],
      document_id: "",
    },
    layouts: [],
    documents: [],
    llmModelItems: [],
  });

  async function fetchCards() {
    state.loading = true;
    try {
      const params = {
        limit: state.itemsPerPage,
        offset: (state.page - 1) * state.itemsPerPage,
      };
      if (state.filters.status) params.status = state.filters.status;
      // Repeated tag=... parameters: a card matches when it carries any selected tag.
      if (state.filters.tags?.length) params.tag = [...state.filters.tags];
      if (state.filters.document_id) params.document_id = state.filters.document_id;
      const res = await getInfoCards(params);
      state.cards = res?.items ?? [];
      state.totalCards = res?.total ?? 0;
    } catch (err) {
      notify.error("Failed to load info cards: " + (err.message || err));
    } finally {
      state.loading = false;
    }
  }

  function onPageOptions({ page, itemsPerPage }) {
    // The server table echoes its current options on mount; that repeats the mount fetch.
    if (page === state.page && itemsPerPage === state.itemsPerPage) return;
    if (itemsPerPage !== state.itemsPerPage) {
      state.itemsPerPage = itemsPerPage;
      state.page = 1;
    } else {
      state.page = page;
    }
    fetchCards();
  }

  function onFilterChange() {
    state.page = 1;
    fetchCards();
  }

  // The document-id filter is typed, so it waits for a pause before fetching.
  let debounceTimer = null;
  function onFilterTyped() {
    clearTimeout(debounceTimer);
    state.page = 1;
    debounceTimer = setTimeout(fetchCards, FILTER_DEBOUNCE_MS);
  }

  async function fetchLayouts() {
    try {
      const res = await getKnowledgeLayouts("info_card");
      state.layouts = res?.layouts ?? [];
    } catch (err) {
      notify.error("Failed to load layouts: " + (err.message || err));
    }
  }

  async function fetchDocuments() {
    try {
      const res = await getKnowledgeDocuments({ limit: PICKER_LIMIT });
      state.documents = res?.items ?? [];
    } catch (_) {
      // The picker stays empty; cards can still be written by hand.
    }
  }

  async function fetchLLMModels() {
    try {
      state.llmModelItems = (await getLLMModels()) ?? [];
    } catch (_) {
      // Generation falls back to the default model.
    }
  }

  async function transition(apiCall, item, done, failed) {
    try {
      await apiCall(item.id);
      notify.success(done);
      await fetchCards();
    } catch (err) {
      notify.error(`${failed}: ` + (err.message || err));
    }
  }

  const approve = (item) =>
    transition(approveInfoCard, item, "Info card approved.", "Failed to approve");
  const archive = (item) =>
    transition(archiveInfoCard, item, "Info card archived.", "Failed to archive");
  const restore = (item) =>
    transition(restoreInfoCard, item, "Info card restored.", "Failed to restore");
  const remove = (item) =>
    transition(deleteInfoCard, item, "Info card deleted.", "Failed to delete");

  return {
    state,
    actions: {
      fetchCards,
      onPageOptions,
      onFilterChange,
      onFilterTyped,
      fetchLayouts,
      fetchDocuments,
      fetchLLMModels,
      approve,
      archive,
      restore,
      remove,
    },
  };
}
