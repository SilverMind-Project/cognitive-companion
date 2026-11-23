import { reactive } from "vue";
import { getKnowledgeDocuments } from "@/services/modules/knowledge";
import { getKnowledgeLayouts } from "@/services/modules/layouts";
import { getLLMModels } from "@/services/modules/pipeline";
import {
  approveQuiz as approveQuizApi,
  archiveQuiz as archiveQuizApi,
  createQuizQuestion,
  deleteQuiz as deleteQuizApi,
  deleteQuizQuestion,
  getQuiz,
  getQuizzes,
  regenerateQuizQuestion,
  reorderQuizQuestions,
  restoreQuiz as restoreQuizApi,
  updateQuizQuestion,
} from "@/services/modules/quizzes";
import { requireNotify } from "@/composables/useNotify.js";

/**
 * State + actions for the Quizzes admin view.
 * Manages server-paginated quiz list, filters, expanded row details,
 * quiz lifecycle transitions, and question operations.
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
      if (state.filters.tags && state.filters.tags.length > 0) {
        params.tags = state.filters.tags.join(",");
      }
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
      const res = await getKnowledgeDocuments({ per_page: 200 });
      state.documents = res?.items ?? [];
    } catch (_err) {
      // non-critical
    }
  }

  async function fetchLLMModels() {
    try {
      state.llmModelItems = (await getLLMModels()) ?? [];
    } catch (_err) {
      // non-critical
    }
  }

  async function fetchExpandedQuiz(quizId) {
    try {
      const detail = await getQuiz(quizId);
      state.expandedQuizzes = {
        ...state.expandedQuizzes,
        [quizId]: detail,
      };
      return detail;
    } catch (_err) {
      state.expandedQuizzes = {
        ...state.expandedQuizzes,
        [quizId]: null,
      };
      return null;
    }
  }

  async function toggleExpand(_event, { item }) {
    const nextRows = new Set(state.expandedRows);
    if (nextRows.has(item.id)) {
      nextRows.delete(item.id);
      const nextExpanded = { ...state.expandedQuizzes };
      delete nextExpanded[item.id];
      state.expandedRows = nextRows;
      state.expandedQuizzes = nextExpanded;
    } else {
      nextRows.add(item.id);
      state.expandedRows = nextRows;
      await fetchExpandedQuiz(item.id);
    }
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
        question_text: "",
        question_type: "multiple_choice",
        choices: [],
        expected_answer: "",
        explanation: "",
      });
      notify.success("Question added.");
      await fetchQuizzes();
    } catch (err) {
      notify.error("Failed to add question: " + (err.message || err));
    }
  }

  async function saveQuestion(quiz, question) {
    try {
      await updateQuizQuestion(quiz.id, question.id, {
        question_text: question.question_text,
        question_type: question.question_type,
        choices: question.choices,
        expected_answer: question.expected_answer,
        explanation: question.explanation,
      });
    } catch (err) {
      notify.error("Failed to update question: " + (err.message || err));
    }
  }

  async function deleteQuestion(quiz, question) {
    try {
      await deleteQuizQuestion(quiz.id, question.id);
      notify.success("Question deleted.");
      await fetchQuizzes();
    } catch (err) {
      notify.error("Failed to delete question: " + (err.message || err));
    }
  }

  async function moveQuestion(quiz, question, direction) {
    try {
      await reorderQuizQuestions(quiz.id, {
        question_id: question?.id,
        direction,
      });
      await fetchQuizzes();
    } catch (err) {
      notify.error("Failed to reorder: " + (err.message || err));
    }
  }

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
      if (suggestion.question_text) question.question_text = suggestion.question_text;
      if (suggestion.choices) question.choices = suggestion.choices;
      if (suggestion.expected_answer) question.expected_answer = suggestion.expected_answer;
      if (suggestion.explanation) question.explanation = suggestion.explanation;
      notify.success("Question regenerated.");
      return suggestion;
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
      toggleExpand,
      approveQuiz,
      archiveQuiz,
      restoreQuiz,
      deleteQuiz,
      addQuestion,
      saveQuestion,
      deleteQuestion,
      moveQuestion,
      regenerateQuestion,
    },
  };
}
