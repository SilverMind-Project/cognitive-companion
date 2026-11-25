import { reactive } from "vue";
import {
  approveQuiz as approveQuizApi,
  archiveQuiz as archiveQuizApi,
  createQuizQuestion,
  deleteQuiz as deleteQuizApi,
  deleteQuizQuestion,
  deleteQuizQuestionImage,
  getQuiz,
  getQuizzes,
  regenerateQuizQuestion,
  reorderQuizQuestions,
  restoreQuiz as restoreQuizApi,
  setQuizQuestionImage,
  updateQuizQuestion,
} from "@/services/modules/quizzes";
import { getKnowledgeDocument, getKnowledgeDocuments } from "@/services/modules/knowledge";
import { getKnowledgeLayouts } from "@/services/modules/layouts";
import { getLLMModels } from "@/services/modules/pipeline";
import { requireNotify } from "@/composables/useNotify.js";
import { normalizeChoices, questionPayload } from "@/components/knowledge/quizChoices.js";

// The list endpoints cap limit at 200.
const PICKER_LIMIT = 200;

/**
 * State + actions for the Quizzes admin view.
 * Manages server-paginated quiz list, filters, expanded row details,
 * quiz lifecycle transitions, and question operations. Adding, deleting, moving, and
 * picture changes re-read the expanded quiz; an in-place field save does not.
 */
export function useQuizzesAdmin({ notify } = {}) {
  requireNotify("useQuizzesAdmin", notify);

  const state = reactive({
    quizzes: [],
    totalQuizzes: 0,
    loading: false,
    error: null,
    page: 1,
    itemsPerPage: 20,
    filters: {
      status: null,
      tags: [],
    },
    documents: [],
    layouts: [],
    llmModelItems: [],
    expandedRows: new Set(),
    expandedQuizzes: {},
    // quiz id -> [{ id, label }] images of that quiz's source document.
    documentImages: {},
  });

  async function fetchQuizzes() {
    state.loading = true;
    state.error = null;
    try {
      const params = {
        limit: state.itemsPerPage,
        offset: (state.page - 1) * state.itemsPerPage,
      };
      if (state.filters.status) params.status = state.filters.status;
      // Repeated tag=... parameters: a quiz matches when it carries any selected tag.
      if (state.filters.tags?.length) params.tag = [...state.filters.tags];
      const res = await getQuizzes(params);
      state.quizzes = res?.items ?? [];
      state.totalQuizzes = res?.total ?? 0;
    } catch (err) {
      state.error = err.message || String(err);
      notify.error("Failed to load quizzes: " + state.error);
    } finally {
      state.loading = false;
    }
  }

  function onPageOptions({ page: newPage, itemsPerPage: newPerPage }) {
    if (newPage === state.page && newPerPage === state.itemsPerPage) return;
    if (newPerPage !== state.itemsPerPage) {
      state.itemsPerPage = newPerPage;
      state.page = 1;
    } else {
      state.page = newPage;
    }
    state.expandedRows = new Set();
    state.expandedQuizzes = {};
    fetchQuizzes();
  }

  function onFilterChange() {
    state.page = 1;
    fetchQuizzes();
  }

  async function fetchLayouts() {
    try {
      const res = await getKnowledgeLayouts("quiz_question");
      state.layouts = res?.layouts ?? [];
    } catch (err) {
      notify.error("Failed to load layouts: " + (err.message || err));
    }
  }

  async function fetchDocuments() {
    try {
      const res = await getKnowledgeDocuments({ limit: PICKER_LIMIT });
      state.documents = res?.items ?? [];
    } catch (err) {
      notify.warning("Could not load documents: " + (err.message || err));
    }
  }

  async function fetchLLMModels() {
    try {
      state.llmModelItems = (await getLLMModels()) ?? [];
    } catch (err) {
      notify.warning("Could not load models: " + (err.message || err));
    }
  }

  function layoutTakesImage(quiz) {
    const layout = state.layouts.find((l) => l.id === quiz?.question_layout_id);
    return Boolean(layout?.max_images);
  }

  async function fetchDocumentImages(quiz) {
    if (!quiz?.document_id || state.documentImages[quiz.id]) return;
    try {
      const doc = await getKnowledgeDocument(quiz.document_id);
      state.documentImages = {
        ...state.documentImages,
        [quiz.id]: (doc?.images ?? []).map((img, i) => ({
          id: img.id,
          label: img.alt_text || `Image ${i + 1}`,
        })),
      };
    } catch (err) {
      notify.warning("Could not load the document's images: " + (err.message || err));
    }
  }

  async function fetchExpandedQuiz(quizId) {
    try {
      const detail = await getQuiz(quizId);
      state.expandedQuizzes = { ...state.expandedQuizzes, [quizId]: detail };
      return detail;
    } catch (err) {
      notify.error("Failed to load quiz: " + (err.message || err));
      state.expandedQuizzes = { ...state.expandedQuizzes, [quizId]: null };
      return null;
    }
  }

  // After a question change: the row shows the stored questions, and the list's question
  // count stays right.
  async function refreshQuiz(quizId) {
    await Promise.all([fetchExpandedQuiz(quizId), fetchQuizzes()]);
  }

  async function setExpanded(ids) {
    const nextRows = new Set(ids);
    const prevRows = state.expandedRows;
    const nextExpanded = { ...state.expandedQuizzes };
    for (const oldId of prevRows) {
      if (!nextRows.has(oldId)) delete nextExpanded[oldId];
    }
    state.expandedRows = nextRows;
    state.expandedQuizzes = nextExpanded;
    for (const id of nextRows) {
      if (!prevRows.has(id) || !state.expandedQuizzes[id]) {
        const detail = await fetchExpandedQuiz(id);
        if (detail) await fetchDocumentImages(detail);
      }
    }
  }

  async function toggleExpand(_event, { item }) {
    const nextRows = new Set(state.expandedRows);
    if (nextRows.has(item.id)) {
      nextRows.delete(item.id);
    } else {
      nextRows.add(item.id);
    }
    await setExpanded([...nextRows]);
  }

  async function approveQuiz(item) {
    try {
      await approveQuizApi(item.id);
      notify.success("Quiz approved.");
      await fetchQuizzes();
    } catch (err) {
      notify.error("Failed to approve: " + (err.message || err));
    }
  }

  async function archiveQuiz(item) {
    try {
      await archiveQuizApi(item.id);
      notify.success("Quiz archived.");
      await fetchQuizzes();
    } catch (err) {
      notify.error("Failed to archive: " + (err.message || err));
    }
  }

  async function restoreQuiz(item) {
    try {
      await restoreQuizApi(item.id);
      notify.success("Quiz restored.");
      await fetchQuizzes();
    } catch (err) {
      notify.error("Failed to restore: " + (err.message || err));
    }
  }

  async function deleteQuiz(item) {
    try {
      await deleteQuizApi(item.id);
      notify.success("Quiz deleted.");
      await fetchQuizzes();
    } catch (err) {
      notify.error("Failed to delete: " + (err.message || err));
    }
  }

  async function addQuestion(quiz) {
    try {
      await createQuizQuestion(quiz.id, {
        question_type: "multiple_choice",
        question_text: "",
        choices: normalizeChoices([{ text: "" }, { text: "" }]),
        expected_answer: "",
        explanation: "",
      });
      notify.success("Question added.");
      await refreshQuiz(quiz.id);
    } catch (err) {
      notify.error("Failed to add question: " + (err.message || err));
    }
  }

  // No re-read here: the card's draft already holds what was saved, and a refetch landing
  // while the caregiver types in another field would overwrite that field.
  async function saveQuestion(quiz, question) {
    try {
      await updateQuizQuestion(quiz.id, question.id, questionPayload(question));
    } catch (err) {
      notify.error("Failed to update question: " + (err.message || err));
    }
  }

  async function deleteQuestion(quiz, question) {
    try {
      await deleteQuizQuestion(quiz.id, question.id);
      notify.success("Question deleted.");
      await refreshQuiz(quiz.id);
    } catch (err) {
      notify.error("Failed to delete question: " + (err.message || err));
    }
  }

  /** Move the question at ``index`` one step (``direction`` -1 up, 1 down). */
  async function moveQuestion(quiz, index, direction) {
    const questions = [...(state.expandedQuizzes[quiz.id]?.questions ?? [])].sort(
      (a, b) => a.ord - b.ord,
    );
    const target = index + direction;
    if (index < 0 || index >= questions.length || target < 0 || target >= questions.length) {
      return;
    }
    const [moved] = questions.splice(index, 1);
    questions.splice(target, 0, moved);
    try {
      await reorderQuizQuestions(
        quiz.id,
        questions.map((q, ord) => ({ id: q.id, ord })),
      );
      await fetchExpandedQuiz(quiz.id);
    } catch (err) {
      notify.error("Failed to reorder: " + (err.message || err));
    }
  }

  async function attachQuestionImage(quiz, question, { file, sourceImageId, altText }) {
    const form = new FormData();
    if (file) form.append("file", file);
    else if (sourceImageId) form.append("source_image_id", String(sourceImageId));
    else return;
    form.append("alt_text", altText || "");
    try {
      await setQuizQuestionImage(quiz.id, question.id, form);
      notify.success("Picture attached.");
      await fetchExpandedQuiz(quiz.id);
    } catch (err) {
      notify.error("Failed to attach the picture: " + (err.message || err));
    }
  }

  async function removeQuestionImage(quiz, question) {
    try {
      await deleteQuizQuestionImage(quiz.id, question.id);
      notify.success("Picture removed.");
      await fetchExpandedQuiz(quiz.id);
    } catch (err) {
      notify.error("Failed to remove the picture: " + (err.message || err));
    }
  }

  /** A regenerated draft of ``question`` (an unsaved suggestion), or null. */
  async function regenerateQuestion(quizId, question, modelId) {
    if (!question?.id) {
      notify.warning("Save the quiz first, then regenerate this question.");
      return null;
    }
    try {
      const quiz = await getQuiz(quizId);
      if (!quiz.document_id) {
        notify.warning("Quiz has no linked document for regeneration.");
        return null;
      }
      const suggestion = await regenerateQuizQuestion(quizId, question.id, modelId || undefined);
      notify.success("Question regenerated. Review it, then save the quiz.");
      return { ...suggestion, choices: normalizeChoices(suggestion.choices) };
    } catch (err) {
      notify.error("Failed to regenerate: " + (err.message || err));
      return null;
    }
  }

  return {
    state,
    actions: {
      fetchQuizzes,
      onPageOptions,
      onFilterChange,
      fetchLayouts,
      fetchDocuments,
      fetchLLMModels,
      fetchExpandedQuiz,
      refreshQuiz,
      setExpanded,
      toggleExpand,
      approveQuiz,
      archiveQuiz,
      restoreQuiz,
      deleteQuiz,
      addQuestion,
      saveQuestion,
      deleteQuestion,
      moveQuestion,
      attachQuestionImage,
      removeQuestionImage,
      regenerateQuestion,
      layoutTakesImage,
    },
  };
}
